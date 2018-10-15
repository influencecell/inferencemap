# -*- coding: utf-8 -*-

# Copyright © 2018, Institut Pasteur
#   Contributor: François Laurent

# This file is part of the TRamWAy software available at
# "https://github.com/DecBayComp/TRamWAy" and is distributed under
# the terms of the CeCILL license as circulated at the following URL
# "http://www.cecill.info/licenses.en.html".

# The fact that you are presently reading this means that you have had
# knowledge of the CeCILL license and that you accept its terms.


from .base import *
from .dv import DV
from .optimization import *
from warnings import warn
from math import pi, log
import numpy as np
import pandas as pd
import scipy.sparse as sparse
from collections import OrderedDict
import time
import numpy.ma as ma


setup = {'name': 'stochastic.dv',
    'provides': 'dv',
    'infer': 'infer_stochastic_DV',
    'arguments': OrderedDict((
        ('localization_error',  ('-e', dict(type=float, help='localization precision (see also sigma; default is 0.03)'))),
        ('diffusivity_prior',   ('-d', dict(type=float, help='prior on the diffusivity'))),
        ('potential_prior',     ('-v', dict(type=float, help='prior on the potential'))),
        ('jeffreys_prior',      ('-j', dict(action='store_true', help="Jeffreys' prior"))),
        ('time_prior',          ('-t', dict(type=float, help='prior on the time'))),
        ('min_diffusivity',     dict(type=float, help='minimum diffusivity value allowed')),
        ('max_iter',            dict(type=int, help='maximum number of iterations (~100)')),
        ('compatibility',       ('-c', '--inferencemap', '--compatible',
                                dict(action='store_true', help='InferenceMAP compatible'))),
        ('epsilon',             dict(args=('--eps',), kwargs=dict(type=float, help='if defined, every gradient component can recruit all of the neighbours, minus those at a projected distance less than this value'), translate=True)),
        ('grad',                dict(help="gradient; any of 'grad1', 'gradn'")),
        ('export_centers',      dict(action='store_true')),
        ('verbose',             ()),
        ('region_size',         ('-s', dict(type=int, help='radius of the regions, in number of adjacency steps'))))),
    'cell_sampling': 'group'}


class LocalDV(DV):
    __slots__ = ('regions','prior_delay','_n_calls')

    def __init__(self, diffusivity, potential, diffusivity_prior=None, potential_prior=None,
        minimum_diffusivity=None, positive_diffusivity=None, prior_include=None,
        regions=None, prior_delay=None):
        # positive_diffusivity is for backward compatibility
        DV.__init__(self, diffusivity, potential, diffusivity_prior, potential_prior,
            minimum_diffusivity, positive_diffusivity, prior_include)
        self.regions = regions
        self.prior_delay = prior_delay
        self._n_calls = 0.

    def region(self, i):
        return self.regions[i]

    def indices(self, cell_ids):
        if isinstance(cell_ids, (int, np.int_)):
                return np.array([ cell_ids, int(self.combined.size / 2) + cell_ids ])
        cell_ids = np.array(cell_ids)
        cell_ids.sort()
        return np.concatenate((cell_ids, int(self.combined.size / 2) + cell_ids))

    def potential_prior(self, i):
        if self.prior_delay:
            if self._n_calls < self.prior_delay:
                prior = None
            else:
                prior = DV.potential_prior(self, i)
            if self._diffusivity_prior:
                self._n_calls += .5
            else:
                self._n_calls += 1.
        else:
                prior = DV.potential_prior(self, i)
        return prior

    def diffusivity_prior(self, i):
        if self.prior_delay:
            if self._n_calls < self.prior_delay:
                prior = None
            else:
                prior = DV.diffusivity_prior(self, i)
            if self._potential_prior:
                self._n_calls += .5
            else:
                self._n_calls += 1.
        else:
                prior = DV.diffusivity_prior(self, i)
        return prior



def make_regions(cells, index, reverse_index, size=1):
    regions = []
    for i in index:
        j = set([i.tolist()])
        j_inner = set()
        for k in range(size):
            j_outer = j - j_inner
            j_inner = j
            for l in j_outer:
                j |= set(cells.neighbours(l).tolist())
        j = reverse_index[list(j)]
        regions.append(j)
    return regions


def local_dv_neg_posterior(j, x, dv, cells, sigma2, jeffreys_prior, \
    time_prior, dt_mean, index, reverse_index, grad_kwargs, y0, verbose, \
    posterior_info, iter_num=None):
    """
    """

    # extract `D` and `V`
    #dv.update(x)
    #D = dv.D # slow
    #V = dv.V
    #Dj = D[j]
    Dj = x[j]
    V = x[int(x.size/2):]
    if np.isnan(Dj):
        raise ValueError('D is nan')
        return 0.
    #

    noise_dt = sigma2

    # for all cell
    i = index[j]
    cell = cells[i]
    n = len(cell) # number of translocations

    # spatial gradient of the local potential energy
    gradV = cells.grad(i, V, reverse_index, **grad_kwargs)
    #print('{}\t{}\t{}\t{}\t{}\t{}'.format(i+1,D[j], V[j], -gradV[0], -gradV[1], result))
    #print('{}\t{}\t{}'.format(i+1, *gradV))
    if gradV is None:
        #raise ValueError('gradV is not defined')
        return 0.

    # various posterior terms
    #print(cell.dt)
    D_dt = Dj * cell.dt
    denominator = 4. * (D_dt + noise_dt)
    dr_minus_drift = cell.dr + np.outer(D_dt, gradV)
    # non-directional squared displacement
    ndsd = np.sum(dr_minus_drift * dr_minus_drift, axis=1)
    raw_posterior = n * log(pi) + np.sum(np.log(denominator)) + np.sum(ndsd / denominator)

    if np.isnan(raw_posterior):
        raise ValueError('undefined posterior')
        #return np.inf

    # priors
    priors = 0.
    potential_prior = dv.potential_prior(j)
    if potential_prior:
        priors += potential_prior * cells.grad_sum(i, gradV * gradV, reverse_index)
    diffusivity_prior = dv.diffusivity_prior(j)
    if diffusivity_prior:
        D = x[:int(x.size/2)]
        # spatial gradient of the local diffusivity
        gradD = cells.grad(i, D, reverse_index, **grad_kwargs)
        if gradD is not None:
            # `grad_sum` memoizes and can be called several times at no extra cost
            priors += diffusivity_prior * cells.grad_sum(i, gradD * gradD, reverse_index)
    #print('{}\t{}\t{}'.format(i+1, D[j], result))
    if jeffreys_prior:
        if Dj <= 0:
            raise ValueError('non positive diffusivity')
        priors += 2. * np.log(Dj * dt_mean[j] + sigma2) - np.log(Dj)

    if time_prior:
        dDdt = cells.time_derivative(i, D, reverse_index)
        # assume fixed-duration time window
        priors += diffusivity_prior * time_prior * dDdt * dDdt
        dVdt = cells.time_derivative(i, V, reverse_index)
        priors += potential_prior * time_prior * dVdt * dVdt

    result = raw_posterior + priors

    if iter_num is None:
        info = [i, raw_posterior, result]
    else:
        info = [iter_num, i, raw_posterior, result]
    posterior_info.append(info)

    return result - y0


def infer_stochastic_DV(cells, diffusivity_prior=None, potential_prior=None, time_prior=None, \
    prior_delay=None, jeffreys_prior=False, min_diffusivity=None, max_iter=None, epsilon=None, \
    export_centers=False, verbose=True, compatibility=False, _stochastic=True, **kwargs):

    # initial values
    if min_diffusivity is not None:
        warn('constraints on diffusivity are not supported', RuntimeWarning)

    index, reverse_index, n, dt_mean, D_initial, min_diffusivity, D_bounds, border = \
        smooth_infer_init(cells, min_diffusivity=min_diffusivity, jeffreys_prior=jeffreys_prior)
    min_diffusivity = None
    try:
        if compatibility:
            raise Exception # skip to the except block
        volume = [ cells[i].volume for i in index ]
    except:
        V_initial = -np.log(n / np.max(n))
    else:
        density = n / np.array([ np.inf if v is None else v for v in volume ])
        density[density == 0] = np.min(density[0 < density])
        V_initial = np.log(np.max(density)) - np.log(density)
    dv = LocalDV(D_initial, V_initial, diffusivity_prior, potential_prior, min_diffusivity, \
        ~border, prior_delay=prior_delay)
    posterior_info = []

    # gradient options
    grad_kwargs = {}
    if epsilon is not None:
        if compatibility:
            warn('epsilon should be None for backward compatibility with InferenceMAP', RuntimeWarning)
        grad_kwargs['eps'] = epsilon

    # parametrize the optimization algorithm
    #default_BFGS_options = dict(maxcor=dv.combined.size, ftol=1e-8, maxiter=1e3,
    #    disp=verbose)
    #options = kwargs.pop('options', default_BFGS_options)
    #if max_iter:
    #    options['maxiter'] = max_iter
    #V_bounds = [(None, None)] * V_initial.size
    if min_diffusivity is None:
        bounds = None
    else:
        bounds = ma.array(np.full(dv.combined.size, min_diffusivity, dtype=float),
            mask=np.r_[np.zeros(D_initial.size, dtype=bool),
                np.ones(V_initial.size, dtype=bool)])

    # posterior function input arguments
    localization_error = cells.get_localization_error(kwargs, 0.03, True)
    args = (dv, cells, localization_error, jeffreys_prior, time_prior, dt_mean,
        index, reverse_index, grad_kwargs)

    # get the initial posterior value so that it is subtracted from the further evaluations (NO)
    # update: x0 may be removed in the future
    m = len(index)
    #x0 = np.sum( local_dv_neg_posterior(j, dv.combined, *(args + (0., False, []))) for j in range(m) )
    #if verbose:
    #    print('At X0\tactual posterior= {}\n'.format(x0))
    x0 = 0.
    args = args + (x0 / float(m), 1 < int(verbose), posterior_info)

    dv.regions = make_regions(cells, index, reverse_index)

    if _stochastic:
        _permutation = np.arange(m)
        def sample(_k, _x): # stochastic
            i = _k % m
            if i == 0:
                np.random.shuffle(_permutation) # in-place
            i = _permutation[i]
            j = dv.region(i)
            return j, dv.indices(i)
    else:
        def sample(_k, _x): # not stochastic
            return np.arange(m), np.arange(2*m)

    # run the optimization routine
    #result = sdfpmin(local_dv_neg_posterior, dv.combined, args, sample, m, verbose=verbose)
    obfgs_kwargs = dict(kwargs)
    if verbose:
        obfgs_kwargs['verbose'] = verbose
    if max_iter:
        obfgs_kwargs['maxiter'] = max_iter
    #if bounds is not None:
    #    obfgs_kwargs['lower_bounds'] = bounds
    rs = [ dv.indices(r) for r in range(len(dv.regions)) ]
    rs += list(rs)
    B = sparse.lil_matrix((dv.combined.size, dv.combined.size), dtype=bool)
    for r in rs:
        B[ np.ix_(r, r) ] = True
    B = B.tocsr()
    obfgs_kwargs['covariates'] = B
    #if 'tau' not in obfgs_kwargs:
    #    obfgs_kwargs['tau'] = 10. * float(D_initial.size)
    #obfgs_kwargs['c'] = .1
    if 'ncomps' not in obfgs_kwargs:
        obfgs_kwargs['ncomps'] = m
    result = minimize_sgbfgs(sample, local_dv_neg_posterior, dv.combined, args, **obfgs_kwargs)
    #if not (result.success or verbose):
    #    warn('{}'.format(result.message), OptimizationWarning)

    dv.update(result.x)
    D, V = dv.D, dv.V
    #if np.any(V < 0):
    #    V -= np.min(V)
    DVF = pd.DataFrame(np.stack((D, V), axis=1), index=index, \
        columns=[ 'diffusivity', 'potential'])

    # derivate the forces
    index_, F = [], []
    for i in index:
        gradV = cells.grad(i, V, reverse_index, **grad_kwargs)
        if gradV is not None:
            index_.append(i)
            F.append(-gradV)
    if F:
        F = pd.DataFrame(np.stack(F, axis=0), index=index_, \
            columns=[ 'force ' + col for col in cells.space_cols ])
    else:
        warn('not any cell is suitable for evaluating the local force', RuntimeWarning)
        F = pd.DataFrame(np.zeros((0, len(cells.space_cols)), dtype=V.dtype), \
            columns=[ 'force ' + col for col in cells.space_cols ])
    DVF = DVF.join(F)

    # add extra information if required
    if export_centers:
        xy = np.vstack([ cells[i].center for i in index ])
        DVF = DVF.join(pd.DataFrame(xy, index=index, \
            columns=cells.space_cols))
        #DVF.to_csv('results.csv', sep='\t')

    # format the posteriors
    if posterior_info:
        cols = ['cell', 'fit', 'total']
        if len(posterior_info[0]) == 4:
            cols = ['iter'] + cols
        posterior_info = pd.DataFrame(np.array(posterior_info), columns=cols)

    if result.err is not None:
        return DVF, posterior_info, pd.DataFrame(result.err, columns=['error'])

    return DVF, posterior_info

