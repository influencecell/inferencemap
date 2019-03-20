# -*- coding:utf-8 -*-

# Copyright © 2017-2019, Institut Pasteur
#    Contributor: Maxime Duval

# This file is part of the TRamWAy software available at
# "https://github.com/DecBayComp/TRamWAy" and is distributed under
# the terms of the CeCILL license as circulated at the following URL
# "http://www.cecill.info/licenses.en.html".

# The fact that you are presently reading this means that you have had
# knowledge of the CeCILL license and that you accept its terms.

import numpy as np
import pandas as pd

import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
import mpl_toolkits.mplot3d as mp3d


def visualize_random_walk(RW, color=True, colorbar=True):
    dim = len(set(RW.columns).intersection({'x', 'y', 'z'}))
    if dim == 1:
        fig, ax = plt.subplots()
        if color:
            points = np.array([RW.t, RW.x]).T.reshape(-1, 1, 2)
            segments = np.concatenate([points[:-1], points[1:]], axis=1)
            norm = plt.Normalize(RW.t.min(), RW.t.max())
            lc = LineCollection(segments, cmap='viridis', norm=norm)
            lc.set_array(RW.t)
            line = ax.add_collection(lc)
            ax.axis('square')
            if colorbar:
                cbar = plt.colorbar(line, ax=ax)
                cbar.set_label('time')
        else:
            line = ax.plot(RW.x)
    elif dim == 2:
        fig, ax = plt.subplots()
        if color:
            points = np.array([RW.x, RW.y]).T.reshape(-1, 1, 2)
            segments = np.concatenate([points[:-1], points[1:]], axis=1)
            norm = plt.Normalize(RW.t.min(), RW.t.max())
            lc = LineCollection(segments, cmap='viridis', norm=norm)
            lc.set_array(RW.t)
            line = ax.add_collection(lc)
            ax.axis('square')
            if colorbar:
                cbar = plt.colorbar(line, ax=ax)
                cbar.set_label('time')
        else:
            line = ax.plot(RW.x, RW.y)
    else:
        fig = plt.figure()
        ax = fig.add_subplot(111, projection='3d')
        if color:
            points = np.array([RW.x, RW.y, RW.z]).T.reshape(-1, 1, 3)
            segments = np.concatenate([points[:-1], points[1:]], axis=1)
            norm = plt.Normalize(RW.t.min(), RW.t.max())
            lc = mp3d.art3d.Line3DCollection(segments, cmap='viridis',
                                             norm=norm)
            lc.set_array(RW.t)
            line = ax.add_collection(lc)
            rmin, rmax = np.min(points), np.max(points)
            ax.set_xlim(rmin, rmax)
            ax.set_ylim(rmin, rmax)
            ax.set_zlim(rmin, rmax)
            if colorbar:
                cbar = plt.colorbar(line, ax=ax)
                cbar.set_label('time')
        else:
            ax.plot(RW.x, RW.y, RW.z)
            ax.set_xlabel('x')
            ax.set_ylabel('y')
            ax.set_zlabel('z')


def visualize_rw_hmm(RW):
    dim = len(set(RW.columns).intersection({'x', 'y', 'z'}))
    nstates = rw.state.max()
    dict_state_color = {}
    for k in range(int(nstates)+1):
        dict_state_color[k] = list({'b', 'g', 'r', 'c', 'm', 'y', 'k', 'w'})[k]

    if dim == 1:
        fig, ax = plt.subplots()
        points = np.array([RW.t, RW.x]).T.reshape(-1, 1, 2)
        segments = np.concatenate([points[:-1], points[1:]], axis=1)
        norm = plt.Normalize(0, nstates)
        lc = LineCollection(segments,
                            colors=[dict_state_color[x] for x in RW.state])
        line = ax.add_collection(lc)
        ax.axis('square')
        manual_legend = [Line2D([0], [0], marker='o', markersize=6, color='w',
                                markerfacecolor=v,
                                label=f'diffusion type {k+1}')
                         for k, v in dict_state_color.items()]
        ax.legend(handles=manual_legend, loc=0)
    elif dim == 2:
        fig, ax = plt.subplots()
        points = np.array([RW.x, RW.y]).T.reshape(-1, 1, 2)
        segments = np.concatenate([points[:-1], points[1:]], axis=1)
        norm = plt.Normalize(0, nstates)
        lc = LineCollection(segments,
                            colors=[dict_state_color[x] for x in RW.state])
        line = ax.add_collection(lc)
        ax.axis('square')
        manual_legend = [Line2D([0], [0], marker='o', markersize=6, color='w',
                                markerfacecolor=v,
                                label=f'diffusion type {k+1}')
                         for k, v in dict_state_color.items()]
        ax.legend(handles=manual_legend, loc=0)
    else:
        fig = plt.figure()
        ax = fig.add_subplot(111, projection='3d')
        points = np.array([RW.x, RW.y, RW.z]).T.reshape(-1, 1, 3)
        segments = np.concatenate([points[:-1], points[1:]], axis=1)
        norm = plt.Normalize(0, nstates)
        lc = mp3d.art3d.Line3DCollection(segments,
                                         colors=[dict_state_color[x]
                                                 for x in RW.state])
        line = ax.add_collection(lc)
        ax.axis('square')
        manual_legend = [Line2D([0], [0], marker='o', markersize=6, color='w',
                                markerfacecolor=v,
                                label=f'diffusion type {k+1}')
                         for k, v in dict_state_color.items()]
        ax.legend(handles=manual_legend, loc=0)
        rmin, rmax = np.min(points), np.max(points)
        ax.set_xlim(rmin, rmax)
        ax.set_ylim(rmin, rmax)
        ax.set_zlim(rmin, rmax)
