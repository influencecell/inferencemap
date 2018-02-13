
from .time import TimeLattice
from tramway.core import isstructured
from tramway.core.hdf5 import *
from collections import OrderedDict
import numpy as np
import pandas as pd


__all__ = ('setup', 'SlidingWindow')


setup = {
	'make_arguments': OrderedDict((
		('duration', dict(type=float, help="window width in seconds (or in frames)")),
		('shift', dict(type=float, help="time shift between consecutive segments, in seconds (or in frames)")),
		('frames', dict(action='store_true', help="regard the --duration and --shift arguments as numbers of frames instead of timestamps")),
		)),
	}


class SlidingWindow(TimeLattice):

	def __init__(self, scaler=None, duration=None, shift=None, frames=False, label=(0, 1)):
		TimeLattice.__init__(self, scaler, label=label)
		if duration is None:
			raise ValueError("'duration' is required")
		elif np.isclose(max(0, duration), 0):
			raise ValueError("'duration' is too short")
		if shift is None:
			shift = duration
		elif np.isclose(max(0, shift), 0):
			raise ValueError("'shift' is too small")
		if frames:
			duration = int(duration)
			shift = int(shift)
		self.duration = duration
		self.shift = shift

	def cell_index(self, points, *args, **kwargs):
		time_col = kwargs.get('time_col', 't')
		if isstructured(points):
			ts = points[time_col]
			if isinstance(ts, (pd.Series, pd.DataFrame)):
				ts = ts.values
		else:
			ts = points[:,time_col]
		t0, t1 = ts.min(), ts.max()
		duration, shift = self.duration, self.shift
		if isinstance(duration, int):
			dt = np.unique(np.diff(np.sort(ts)))
			if dt[0] == 0:
				dt = dt[1]
			else:
				dt = dt[0]
			duration *= dt
			shift *= dt
			dt /= 10.
		else:
			dt = 1e-7 # precision down to a microsecond (quantum < microsecond)
		nsegments = np.floor((t1 - t0 - duration) / shift) + 1.
		t1 = t0 + (nsegments - 1.) * shift + duration
		t0s = np.arange(t0, t1 - duration + dt, shift)
		t1s = t0s + duration + dt
		self.time_lattice = np.stack((t0s, t1s), axis=-1)
		return TimeLattice.cell_index(self, points, *args, **kwargs)


import sys
if sys.version_info[0] < 3:

	sliding_window_exposes = time_lattice_exposes + ['duration', 'shift']
	hdf5_storable(default_storable(SlidingWindow, exposes=sliding_window_exposes), agnostic=True)

	__all__ = __all__ + ('sliding_window_exposes', )
