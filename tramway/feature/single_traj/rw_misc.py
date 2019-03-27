# -*- coding:utf-8 -*-

# Copyright © 2017-2019, Institut Pasteur
#    Contributor: Maxime Duval

# This file is part of the TRamWAy software available at
# "https://github.com/DecBayComp/TRamWAy" and is distributed under
# the terms of the CeCILL license as circulated at the following URL
# "http://www.cecill.info/licenses.en.html".

# The fact that you are presently reading this means that you have had
# knowledge of the CeCILL license and that you accept its terms.

"""
This module regroups helper functions for random walk simulations
"""

import numpy as np

SPACE_COLS = ['x', 'y', 'z']


def rw_is_useless(rw):
    is_immobile = True
    n = 0
    while 2**n <= len(rw):
        if len(rw.iloc[:2**n].x.unique()) > 1:
            return False
        n += 1
    return is_immobile


def normalize_init(X, dim):
    """
    Small function to normalize the starting point of the random walk.

    Parameters
    ----------
    X : float or list, the starting point.
    dim : int, in {1,2,3}, the dimension of the random walk.
    """
    if type(X) != list:
        if X is None:
            X = 0
        return [X] * dim
    else:
        if len(X) < dim:
            return X + [0] * (dim - len(X))
        elif len(X) == dim:
            return X
        else:
            return X[:dim]


def apply_angle_dists(dist, angle, dim):
    """
    Applies a distribution of angles to a distribution of distances to generate
    the positions of the random walk in the right dimensions

    Parameters
    ----------
    dist : array of non negative values
    angle : array of angles.
    dim : the dimension of the random walk.
        If dim = 0, then angle needs to be a random array of 0 and 1.
        If dim = 1, then angle needs to be a random array of numbers between
            0 and 2pi.
        If dim = 2, then angle needs to be a 2d array, with the first line
            containing random angles between 0 and pi and the second line
            containing random angles between 0 and 2pi.
    """
    if dim == 1:
        X = dist * angle
        return np.expand_dims(X, axis=0)
    elif dim == 2:
        X = dist * np.cos(angle)
        Y = dist * np.sin(angle)
        return np.vstack((X, Y))
    elif dim == 3:
        X = dist * np.sin(angle[0]) * np.cos(angle[1])
        Y = dist * np.sin(angle[0]) * np.sin(angle[1])
        Z = dist * np.cos(angle[0])
        return np.vstack((X, Y, Z))


def regularize_times(X_raw, t_raw, t_regular):
    """
    This function is used to regularize times generated from some distribution
    to constant spaced times.

    Parameters
    ----------
    X_raw : numpy array, position of the random walk at different times, given
        by t_raw.
    t_raw : raw times, distribution of times : non constant delta ts.
    t_regular : the times (with constant delta t) at which we want the position
        of the random walk.

    Returns
    -------
    X : regularized X_raw, with position of the random walk at each t in
        t_regular.
    t_regular : times for which we have the position of the random walk. Can be
        shorter than the t_regular input if the maximum time in t_raw is higher
        than the maximum time in the input t_regular.
    """
    diff_t = t_regular[:, np.newaxis] - t_raw[np.newaxis, :]
    indice_array = (np.argmin(diff_t >= 0, axis=1) - 1)
    imin = np.argmin(indice_array)
    if indice_array[imin] == -1:
        t_regular = t_regular[:imin]
        X = X_raw[indice_array[:imin]]
    else:
        X = X_raw[indice_array]
    return X, t_regular


# For confined movement (RW_circular_confinement)


def cart2pol(x, y):
    rho = np.sqrt(x**2 + y**2)
    phi = np.arctan2(y, x)
    return rho, phi


def cart2spher(x, y, z):
    r = np.sqrt(x * x + y * y + z * z)
    phi = np.arctan2(y, x)
    theta2 = np.arccos(z / (r + 1e-8))
    return r, phi, theta2


def local_border_forces_1D(r, d_wall, sigma, V_confinement):
    f = 0
    f_slope = V_confinement/sigma
    H_f = np.heaviside(np.abs(r) - d_wall + sigma, 1)
    f = H_f * (-np.sign(r) * f_slope)
    return f


def local_border_forces_2D(r, d_wall, theta, sigma, V_confinement):
    f = np.zeros((2,))
    f_slope = V_confinement / sigma
    H_f = np.heaviside(r - d_wall + sigma, 1)
    f[0] = H_f * (-r * np.cos(theta) * f_slope)
    f[1] = H_f * (-r * np.sin(theta) * f_slope)
    return f


def local_border_forces_3D(r, d_wall, theta, phi, sigma, V_confinement):
    f = np.zeros((3,))
    f_slope = V_confinement/sigma
    H_f = np.heaviside(r - d_wall + sigma, 1)
    f[0] = H_f * (- r * np.sin(theta) * np.cos(phi) * f_slope)
    f[1] = H_f * (- r * np.sin(theta) * np.sin(phi) * f_slope)
    f[2] = H_f * (- r * np.cos(theta) * f_slope)
    return f

# For Self Avoiding Random Walks

# Basic Functions


def pluss(pt_1, pt_2, dim):
    pt = []
    for coordinate in range(dim):
        pt.append(pt_1[coordinate] + pt_2[coordinate])
    return tuple(pt)


def moinss(pt_1, pt_2, dim):
    pt = []
    for coordinate in range(dim):
        pt.append(pt_1[coordinate] - pt_2[coordinate])
    return tuple(pt)


def norme_manhattan(pt):
    resul = 0
    for coord in pt:
        resul += abs(coord)
    return resul


def enleve_coord(pt, coordinate):
    pt = list(pt)
    pt.pop(coordinate)
    return tuple(pt)


def voisin(pt, coord, ecart):
    resul = list(pt)
    resul[coord] = resul[coord] + ecart
    return tuple(resul)


def intersection(ensemble_1, ensemble_2):
    resul = []
    for v in ensemble_1:
        if v in ensemble_2:
            resul.append(v)
    return resul


def distance_euclidean(pt1, pt2, dim):
    resul = 0
    for coordinate in range(dim):
        resul += ((pt1[coordinate] - pt2[coordinate]) ** 2)
    return math.sqrt(resul)


# Create network


def create_minmax(dim, Petite_Origine):
    les_minmax = []
    for i in range(dim):
        les_minmax.append({Petite_Origine: [0, 0]})
    return les_minmax


def create_deplacement(dim):
    deplacements = []
    for i in range(dim):
        deplacements.append(tuple(([0] * i) + [1] + ([0] * (dim - (i + 1)))))
        deplacements.append(tuple(([0] * i) + [-1] + ([0] * (dim - (i + 1)))))
    return deplacements


def construct_chemin(graphe, distance, v):
    ch = [v]
    d = distance[v]
    x = v
    while d > 0:
        for y in graphe[x]:
            if distance[y] == d - 1:
                ch.append(y)
                d -= 1
                x = y
                break
    return ch


def chemin(depart, arrivees, graphe):
    distance = {}
    for vertice in graphe:
        distance[vertice] = None
    distance[depart] = 0
    frontiere = [depart]
    k = 1
    while frontiere != []:
        new_front = []
        for vertice in frontiere:
            for vertice_2 in graphe[vertice]:
                if vertice_2 in arrivees:
                    distance[vertice_2] = k
                    return construct_chemin(graphe, distance, vertice_2)
                if distance[vertice_2] is None:
                    distance[vertice_2] = k
                    new_front.append(vertice_2)
        k += 1
        frontiere = new_front


def calcul_proba(tab, bias, dim):
    resul = []
    for coordinate in range(len(tab)):
        if tab[coordinate] >= 0:
            if bias == 0:
                resul.append(coordinate)
            elif bias > 0:
                resul.extend([coordinate] * (bias - 1 + tab[coordinate]))
            else:
                resul.extend([coordinate] * (-bias + (2 * dim) - 1 -
                                             tab[coordinate]))
    return resul


# For Random Walks on Pattern : Pattern creation


PATTERN_SIERPINSKI = {
    "classic": np.array([[1, 1, 0],
                         [1, 1, 1],
                         [0, 1, 0]]),
    "butterfly": np.array([[1, 1, 0],
                           [1, 1, 1],
                           [0, 1, 1]]),
    "stairs": np.array([[1, 0, 0],
                        [1, 1, 0],
                        [1, 1, 1]]),
    "cross5": np.array([[1, 1, 1, 1, 1],
                        [1, 0, 1, 0, 1],
                        [1, 1, 1, 1, 1],
                        [1, 0, 1, 0, 1],
                        [1, 1, 1, 1, 1]]),
    "square5": np.array([[0, 1, 1, 1, 0],
                         [0, 1, 1, 1, 0],
                         [1, 1, 1, 1, 1],
                         [0, 1, 1, 1, 0],
                         [0, 1, 1, 1, 0]]),
    "square5_full": np.array([[0, 1, 1, 1, 0],
                              [1, 0, 1, 0, 1],
                              [1, 1, 1, 1, 1],
                              [1, 0, 1, 0, 1],
                              [0, 1, 1, 1, 0]]),
    "cheese5": np.array([[1, 0, 1, 0, 1],
                         [1, 1, 1, 1, 1],
                         [1, 1, 1, 1, 1],
                         [1, 1, 1, 1, 1],
                         [1, 0, 1, 0, 1]])
}


def sierpinski_carpet_deterministic_generator(global_iteration=4,
                                              nature="classic",
                                              path_output=None):
    base_pattern = PATTERN_SIERPINSKI[nature]
    base_size = base_pattern.shape[0]
    n_2 = int(np.floor(base_size/2))
    matrice_zeros = np.zeros((base_size, base_size), dtype=int)
    pattern = base_pattern
    for _ in range(global_iteration):
        ll = pattern.shape[0]
        pattern_new = np.zeros((base_size * ll, base_size * ll))
        for i in range(ll):
            for j in range(ll):
                i_mean = (i)*base_size + base_size - (n_2+1)
                j_mean = (j)*base_size + base_size - (n_2+1)
                if pattern[i, j] == 0:
                    pattern_new[i_mean-n_2:i_mean+n_2+1,
                                j_mean-n_2:j_mean+n_2+1] = matrice_zeros
                else:
                    pattern_new[i_mean-n_2:i_mean+n_2+1,
                                j_mean-n_2:j_mean+n_2+1] = base_pattern
        pattern = pattern_new
    if path_output is not None:
        np.save(path_output, pattern)
    return pattern


def generate_the_fractals_and_save_them(DIR, types=[(7, "classic"),
                                                    (7, "butterfly"),
                                                    (5, "cross5"),
                                                    (5, "square5_full"),
                                                    (5, "cheese5")]):
    for (num_iter, type_name) in types:
        sierpinski_carpet_deterministic_generator(
            global_iteration=num_iter,
            nature=type_name,
            path_output=f'{DIR}\{type_name}')


def update_position(motif, i_init, j_init):
    keep_going = True
    counter = 0
    output_loc = np.zeros((4, 2), dtype=int)

    if motif[i_init+1, j_init] == 1:
        output_loc[counter, 0] = i_init+1
        output_loc[counter, 1] = j_init
        counter += 1
    if motif[i_init, j_init+1] == 1:
        output_loc[counter, 0] = i_init
        output_loc[counter, 1] = j_init+1
        counter += 1
    if motif[i_init-1, j_init] == 1:
        output_loc[counter, 0] = i_init-1
        output_loc[counter, 1] = j_init
        counter += 1
    if motif[i_init, j_init-1] == 1:
        output_loc[counter, 0] = i_init
        output_loc[counter, 1] = j_init-1
        counter += 1

    if counter == 0:
        k = 0
        l = 0
        keep_going = False
    else:
        counter_alea = np.random.randint(counter)
        k = output_loc[counter_alea, 0]
        l = output_loc[counter_alea, 1]
    return k, l, keep_going
