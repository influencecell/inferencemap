# -*- coding: utf-8 -*-

# Copyright © 2020, Institut Pasteur
#   Contributor: François Laurent

# This file is part of the TRamWAy software available at
# "https://github.com/DecBayComp/TRamWAy" and is distributed under
# the terms of the CeCILL license as circulated at the following URL
# "http://www.cecill.info/licenses.en.html".

# The fact that you are presently reading this means that you have had
# knowledge of the CeCILL license and that you accept its terms.


from .abc import *
from ..attribute import *
from tramway.core.xyt import crop
from . import collections as helper
import warnings
import numpy as np
from collections.abc import Sequence, Set
from tramway.tessellation.base import Partition
from rwa.lazy import lazytype


class BaseRegion(AnalyzerNode):
    """
    This class should not be directly instanciated.
    It brings the basic functionalities to all the available representations
    of regions of interest, merely labelling, analysis registration and time cropping.
    """
    __slots__ = ('_spt_data','_label')
    def __init__(self, spt_data, label=None, **kwargs):
        AnalyzerNode.__init__(self, **kwargs)
        self._spt_data = spt_data
        self._label = label
    @property
    def label(self):
        if callable(self._label):
            self._label = self._label()
        return self._label
    def get_sampling(self, label=None, unique=True, _type=Partition):
        if callable(label):
            label = label(self.label)
        elif label is None:
            label = self.label
        if isinstance(label, str):
            labels = [label]
        else:
            labels = list(label)
        analyses = [ self._spt_data.get_sampling(_label) for _label in labels ]
        if _type:
            analyses = [ a for a in analyses if issubclass(lazytype(a._data), _type) ]
        if unique:
            if analyses[1:]:
                raise ValueError('label is not specific enough; multiple samplings match')
            elif not analyses:
                raise KeyError("could not find label '{}'".format(label))
            return analyses[0]
        else:
            return analyses
    def add_sampling(self, sampling, label=None, comment=None):
        if callable(label):
            label = label(self.label)
        elif label is None:
            label = self.label
        return self._spt_data.add_sampling(sampling, label, comment)
    def autosaving(self, *args, **kwargs):
        return self._spt_data.autosaving(*args, **kwargs)
    def discard_static_trajectories(self, df, **kwargs):
        return self._spt_data.discard_static_trajectories(df, **kwargs)
    @property
    def _mpl_impl(self):
        from .mpl import Mpl
        return Mpl
    @property
    def mpl(self):
        return self._mpl_impl(self)

class IndividualROI(BaseRegion):
    """ for typing only """
    __slots__ = ()
    pass

class BoundingBox(IndividualROI):
    """ See :class:`BoundingBoxes`. """
    __slots__ = ('_bounding_box',)
    def __init__(self, bb, label, spt_data, **kwargs):
        IndividualROI.__init__(self, spt_data, label, **kwargs)
        self._bounding_box = bb
    def crop(self, df=None):
        _min,_max = self._bounding_box
        if df is None:
            df = self._spt_data.dataframe
        df = crop(df, np.r_[_min, _max-_min])
        return df
    @property
    def bounding_box(self):
        return self._bounding_box
    def crop_frames(self, **kwargs):
        """
        Iterates and crops the image frames.

        `kwargs` are passed to images' :meth:`~tramway.analyzer.images.abc.Images.crop_frames` method.
        """
        yield from self._spt_data.get_image().crop_frames(self.bounding_box, **kwargs)

class SupportRegion(BaseRegion):
    """
    union of overlapping ROI.
    """
    __slots__ = ('_sr_index','_support_regions')
    def __init__(self, r, regions, spt_data, **kwargs):
        BaseRegion.__init__(self,
                spt_data,
                r if isinstance(r, str) else regions.region_label(r),
                **kwargs)
        self._sr_index = r
        self._support_regions = regions
    def crop(self, df=None):
        if df is None:
            df = self._spt_data.dataframe
        df = self._support_regions.crop(self._sr_index, df)
        return df
    @property
    def bounding_box(self):
        if isinstance(self._support_regions, helper.UnitRegions):
            return self._support_regions[self._sr_index]
        else:
            minima, maxima = zip(*[ self._support_regions.unit_region[u] \
                for u in self._support_regions[self._sr_index] ])
            return np.min(np.stack(minima, axis=0), axis=0), np.max(np.stack(maxima, axis=0), axis=0)
    def crop_frames(self, **kwargs):
        """
        Iterates and crops the image frames, based on `bounding_box`.

        `kwargs` are passed to images' :meth:`~tramway.analyzer.images.abc.Images.crop_frames` method.
        """
        yield from BoundingBox.crop_frames(self, **kwargs)

class FullRegion(BaseRegion):
    """
    wraps the full dataset; does not actually crop.

    A `FullRegion` can be both an individual ROI and a support region.
    """
    __slots__ = ()
    def crop(self, df=None):
        if df is None:
            df = self._spt_data.dataframe
        return df
    def crop_frames(self, **kwargs):
        """
        .. note:

            Time cropping is not supported yet.

        """
        if self.time_support is not None:
            self._eldest_parent.logger.warning('time cropping is not supported yet')
        yield from self._spt_data.as_frames(**kwargs)


class DecentralizedROIManager(AnalyzerNode):
    """
    This class allows to iterate over the ROI defined at the level of
    each SPT data item.
    """
    __slots__ = ('_records',)
    def __init__(self, first_record=None, **kwargs):
        AnalyzerNode.__init__(self, **kwargs)
        self._records = set()
        if first_record is not None:
            self._register_decentralized_roi(first_record)
    def _register_decentralized_roi(self, has_roi):
        if isinstance(has_roi.roi, ROIInitializer):
            self._parent.logger.warning('cannot register an uninitialized ROI attribute')
            return
        self._records.add(has_roi)
        has_roi.roi._global = self
    def _update_decentralized_roi(self, known_record, new_record):
        self._records.remove(known_record)
        self._register_decentralized_roi(new_record)
    def reset(self):
        self._records = set()
    def self_update(self, op):
        raise NotImplementedError('why for?')
        self._parent._roi = op(self)
    def as_individual_roi(self, index=None, collection=None, source=None, **kwargs):
        """ Generator function; loops over all the individual roi.

        Filtering is delegated to the individual *SPTDataItem.roi* attributes.

        A *callable* filter takes a single key (*int* for indices, *str* for labels and paths)
        and returns a *bool*.
        
        Arguments:
            
            index (*int*, *set* of *int*, *sequence* of *int*, or *callable*):
                individual ROI index filter; indices apply within a collection
                
            collection (*str*, *set* of *str*, *sequence* of *str*, or *callable*):
                collection label filter
            
            source (*str*, *set* of *str*, *sequence* of *str*, or *callable*):
                SPT data source filter
            
        """
        if source is None:
            for rec in self._records:
                yield from rec.roi.as_individual_roi(index, collection, **kwargs)
        else:
            if callable(source):
                sfilter = source
            else:
                sfilter = lambda s: s==source
            for rec in self._records:
                if sfilter(rec.source):
                    yield from rec.roi.as_individual_roi(index, collection, **kwargs)
    def as_support_regions(self, index=None, source=None, **kwargs):
        """ Generator function; loops over all the support regions.

        Support regions are equivalent to individual ROI if *group_overlapping_roi*
        was set to :const:`False`.

        Filtering is delegated to the individual *SPTDataItem.roi* attributes.

        A *callable* filter takes a single key (*int* for indices, *str* for paths)
        and returns a *bool*.
        
        Arguments:
            
            index (*int*, *set* of *int*, *sequence* of *int*, or *callable*):
                support region index filter
            
            source (*str*, *set* of *str*, *sequence* of *str*, or *callable*):
                SPT data source filter
                
        """
        if source is None:
            for rec in self._records:
                yield from rec.roi.as_support_regions(index, **kwargs)
        else:
            if callable(source):
                sfilter = source
            else:
                sfilter = lambda s: s==source
            for rec in self._records:
                if sfilter(rec.source):
                    yield from rec.roi.as_support_regions(index, **kwargs)
    def __iter__(self):
        raise AttributeError(type(self).__name__+' object is not iterable; call methods as_support_regions() or as_individual_roi()')

ROI.register(DecentralizedROIManager)


class ROIInitializer(Initializer):
    """
    Initial value for the :class:`~tramway.analyzer.RWAnalyzer`
    :attr:`~tramway.analyzer.RWAnalyzer.roi` attribute.

    `from_...` methods alters the parent attribute which specializes
    into an initialized :class:`ROI` object.
    """
    __slots__ = ()
    def specialize(self, cls, *args, **kwargs):
        Initializer.specialize(self, cls, *args, **kwargs)
        if self._parent is self._eldest_parent and not issubclass(cls, DecentralizedROIManager):
            # replace all individual-SPT-item-level roi initializers by mirrors
            spt_data, roi = self._parent.spt_data, self._parent.roi
            if not spt_data.initialized:
                raise RuntimeError('cannot define ROI as long as the `spt_data` attribute is not initialized')
            for f in spt_data:
                assert isinstance(f, HasROI)
                if f.roi.initialized:
                    raise RuntimeError('ROI already defined at the individual SPT data item level')
                f.roi._from_common_roi(roi)
    ## initializers
    def _from_common_roi(self, roi):
        # special `specialize`
        spt_data = self._parent
        spt_data._roi = spt_data._bear_child( CommonROI, roi )
    def _register_decentralized_roi(self, roi):
        self.specialize( DecentralizedROIManager, roi )
    def from_bounding_boxes(self, bb, label=None, group_overlapping_roi=False):
        """
        Defines ROI as bounding boxes.

        Arguments:

            bb (sequence): collection of bounding boxes, each bounding boxes being
                a pair of lower and upper bounds (*numpy.ndarray*)

            label (str): unique label for the collection

            group_overlapping_roi (bool): if :const:`False`, :meth:`as_support_regions`
                will behave similarly to :meth:`as_individual_roi`, otherwise support
                regions are unions of overlapping ROI

        See also :class:`BoundingBoxes`.
        """
        self.specialize( BoundingBoxes, bb, label, group_overlapping_roi )
    def from_squares(self, centers, side, label=None, group_overlapping_roi=False):
        """
        Defines ROI as centers for squares/cubes of uniform size.

        See also :meth:`from_bounding_boxes`.
        """
        bb = [ (center-.5*side, center+.5*side) for center in centers ]
        self.from_bounding_boxes(bb, label, group_overlapping_roi)
    ## in the case no ROI are defined
    def as_support_regions(self, index=None, source=None, return_index=False):
        """ Generator function; loops over all the support regions.
        
        A :class:`ROIInitializer` does not define any ROI,
        as a consequence a single :class:`FullRegion` object is yielded."""
        if not null_index(index):
            raise ValueError('no ROI defined; cannot seek for the ith ROI')
        if return_index:
            def bear_child(*args):
                return 0, self._bear_child(*args)
        else:
            bear_child = self._bear_child
        try:
            spt_data = self._parent.spt_data
        except AttributeError:
            # decentralized roi (single source)
            if source is not None:
                warnings.warn('ignoring argument `source`', helper.IgnoredInputWarning)
            spt_data = self._parent
            yield bear_child( FullRegion, spt_data )
        else:
            # roi manager (multiple sources)
            if isinstance(spt_data, Initializer):
                raise RuntimeError('cannot iterate not-initialized SPT data')
            if source is None:
                for d in spt_data:
                    yield bear_child( FullRegion, d )
            else:
                if callable(source):
                    sfilter = source
                else:
                    sfilter = lambda s: s==source
                for d in spt_data:
                    if sfilter(d.source):
                        yield bear_child( FullRegion, d )
    def as_individual_roi(self, index=None, collection=None, source=None, **kwargs):
        """ Generator function; loops over all the individual ROI.
        
        A :class:`ROIInitializer` does not define any ROI,
        as a consequence a single :class:`FullRegion` object is yielded."""
        if collection is not None:
            warnings.warn('ignoring argument `collection`', helper.IgnoredInputWarning)
        return self.as_support_regions(index, source, **kwargs)
    def __iter__(self):
        raise AttributeError(type(self).__name__+' object is not iterable; call methods as_support_regions() or as_individual_roi()')

ROI.register(ROIInitializer)


class CommonROI(AnalyzerNode):
    """
    Mirrors the global :attr:`~tramway.analyzer.RWAnalyzer.roi` attribute.

    The individual *SPTDataItem.roi* attributes become :class:`CommonROI` objects
    as soon as the global :attr:`~tramway.analyzer.RWAnalyzer.roi` attribute is
    specialized, so that :meth:`as_support_regions` and :meth:`as_individual_roi`
    iterators delegate to the global attribute.
    """
    __slots__ = ('_global',)
    def __init__(self, roi, parent=None):
        AnalyzerNode.__init__(self, parent)
        self._global = roi
    def as_support_regions(self, index=None, source=None, return_index=False):
        spt_data = self._parent
        if not spt_data.compatible_source(source):
            warnings.warn('ignoring argument `source`', helper.IgnoredInputWarning)
            return
        yield from self._global.as_support_regions(index, spt_data.source, return_index)
    def self_update(self, op):
        raise RuntimeError('cannot alter a mirror attribute')
    def as_individual_roi(self, index=None, collection=None, source=None, return_index=False):
        spt_data = self._parent
        if not spt_data.compatible_source(source):
            warnings.warn('ignoring argument `source`', helper.IgnoredInputWarning)
            return
        yield from self._global.as_individual_roi(index, collection, spt_data.source, return_index)
    def __iter__(self):
        raise AttributeError(type(self).__name__+' object is not iterable; call methods as_support_regions() or as_individual_roi()')


class SpecializedROI(AnalyzerNode):
    """
    Basis for initialized :class:`ROI` classes.
    """
    __slots__ = ('_global','_collections')
    def __init__(self, **kwargs):
        AnalyzerNode.__init__(self, **kwargs)
        self._global = None
        self._collections = None
    def self_update(self, op):
        self._parent._roi = op(self)
        assert self._global is not None
        if self._global is not None:
            # parent spt_data object should still be registered
            assert self._parent in self._global._records
    def as_support_regions(self, index=None, source=None, return_index=False):
        if return_index:
            def bear_child(cls, r, *args):
                i, r = r
                return i, self._bear_child(cls, r, *args)
            kwargs = dict(return_index=return_index)
        else:
            bear_child = self._bear_child
            kwargs = {}
        try:
            spt_data = self._parent.spt_data
        except AttributeError:
            # decentralized roi (single source)
            if source is not None:
                warnings.warn('ignoring argument `source`', helper.IgnoredInputWarning)
            spt_data = self._parent
            for r in indexer(index, self._collections.regions, **kwargs):
                yield bear_child( SupportRegion, r, self._collections.regions, spt_data )
        else:
            # roi manager (one set of regions, multiple sources)
            if isinstance(spt_data, Initializer):
                raise RuntimeError('cannot iterate not-initialized SPT data')
            if source is None:
                for d in spt_data:
                    for r in indexer(index, self._collections.regions, **kwargs):
                        yield bear_child( SupportRegion, r, self._collections.regions, d )
            else:
                if callable(source):
                    sfilter = source
                else:
                    sfilter = lambda s: s==source
                for d in spt_data:
                    if sfilter(d.source):
                        for r in indexer(index, self._collections.regions, **kwargs):
                            yield bear_child( SupportRegion, r, self._collections.regions, d )
    as_support_regions.__doc__ = ROI.as_support_regions.__doc__
    def __iter__(self):
        raise AttributeError(type(self).__name__+' object is not iterable; call methods as_support_regions() or as_individual_roi()')

class BoundingBoxes(SpecializedROI):
    """
    Bounding boxes are a list of pairs of NumPy row arrays (1xD).

    The first array specifies the lower bounds, the second array the upper bounds.
    """
    __slots__ = ('_bounding_boxes',)
    def __init__(self, bb, label=None, group_overlapping_roi=False, **kwargs):
        SpecializedROI.__init__(self, **kwargs)
        self._collections = helper.Collections(group_overlapping_roi)
        if label is None:
            label = ''
        self._collections[label] = bb
        self._bounding_boxes = {label: bb}
    @property
    def bounding_boxes(self):
        return self._bounding_boxes
    def as_individual_roi(self, index=None, collection=None, source=None, return_index=False):
        if return_index:
            def bear_child(i, *args):
                return i, self._bear_child(*args)
        else:
            def bear_child(i, *args):
                return self._bear_child(*args)
        try:
            spt_data = self._parent.spt_data
        except AttributeError:
            # decentralized roi (single source)
            if source is not None:
                warnings.warn('ignoring argument `source`', helper.IgnoredInputWarning)
            spt_data = self._parent
            for label in indexer(collection, self.bounding_boxes):
                for i, bb in indexer(index, self.bounding_boxes[label], return_index=True):
                    roi_label = self._collections[label].roi_label(i)
                    yield bear_child(i, BoundingBox, bb, roi_label, spt_data )
        else:
            for d in spt_data:
                for label in indexer(collection, self.bounding_boxes):
                    for i, bb in indexer(index, self.bounding_boxes[label], return_index=True):
                        roi_label = self._collections[label].roi_label(i)
                        yield bear_child(i, BoundingBox, bb, roi_label, d )
    as_individual_roi.__doc__ = ROI.as_individual_roi.__doc__
    @property
    def index_format(self):
        """
        *str*: Format of the numeric part of the label
        """
        return self._collections.numeric_format
    @index_format.setter
    def index_format(self, fmt):
        self._collections.numeric_format = fmt
    def set_num_digits(self, n):
        """
        Sets the number of digits in the numeric part of the label.
        """
        if not isinstance(n, int):
            raise TypeError('num_digits is not an int')
        self.index_format = n

ROI.register(BoundingBoxes)


class HasROI(AnalyzerNode):
    """ Class to be inherited from by SPT data item classes.
    
    Maintains a self-modifying *roi* attribute."""
    __slots__ = ('_roi',)
    def _get_roi(self):
        """
        *ROI*: Regions of interest for the parent data block
        """
        return self._roi
    def _set_roi(self, roi):
        self._roi = roi
        global_roi_attr = self._eldest_parent.roi
        if global_roi_attr.initialized:
            assert isinstance(global_roi_attr, DecentralizedROIManager)
        global_roi_attr._register_decentralized_roi(self)
    roi = selfinitializing_property('roi', _get_roi, _set_roi, ROI)

    def __init__(self, roi=ROIInitializer, **kwargs):
        AnalyzerNode.__init__(self, **kwargs)
        self._roi = roi(self._set_roi, parent=self)
    def compatible_source(self, source):
        """
        returns :const:`True` if filter *source* matches with `self.source`.

        .. note::

            does not check against the alias.

        """
        if source is None:
            return True
        elif callable(source):
            return source(spt_data.source)
        elif isinstance(source, str):
            return source == spt_data.source
        elif isinstance(source, (Set, Sequence)):
            return spt_data.source in source
        else:
            raise NotImplementedError


__all__ = [ 'ROI', 'ROIInitializer', 'SpecializedROI', 'BoundingBoxes', 'DecentralizedROIManager',
        'BaseRegion', 'FullRegion', 'IndividualROI', 'BoundingBox', 'SupportRegion',
        'CommonROI', 'HasROI' ]

