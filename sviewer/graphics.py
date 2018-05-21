# -*- coding: utf-8 -*-
"""
Created on Thu Dec 22 11:38:59 2016

@author: Serj
"""
import astropy.constants as ac
from astropy.convolution import convolve, Gaussian1DKernel, Gaussian2DKernel
from astropy.modeling.models import Moffat1D
from bisect import bisect_left
from ccdproc import cosmicray_lacosmic
from copy import deepcopy
import itertools
from matplotlib.cm import get_cmap
import matplotlib.pyplot as plt
import numpy as np
from numpy.lib.stride_tricks import as_strided
import os
import pyqtgraph as pg
from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QFont, QColor, QBrush
from PyQt5.QtWidgets import QApplication
import re
from scipy.interpolate import interp1d, splrep, splev
from scipy.optimize import curve_fit
from scipy.stats import gaussian_kde

from ..profiles import tau, convolveflux, makegrid
from .external import sg_smooth as sg
from .utils import Timer, debug, MaskableList, moffat_func

class Speclist(list):
    def __init__(self, parent):
        self.parent = parent
        self.ind = None
            
    def draw(self):
        self[self.ind].view = self.parent.specview
        for i, s in enumerate(self):
            if i != self.ind:
                s.init_GU()
        self[self.ind].init_GU()
        self.parent.vb.enableAutoRange()
        
    def redraw(self, ind=None):
        """
        procedure for redraw spectra: 
            if <ind> is provided then redraw only <current> and <ind> spectra.
        """
        if len(self) > 0:
            if ind == None:
                for i, s in enumerate(self):
                    if i != self.ind:
                        s.redraw()
                self[self.ind].redraw()
            else:
                saved_ind = self.ind
                self.ind = ind
                self[saved_ind].redraw()
                self[self.ind].redraw()

    def remove(self, ind=None):
        if ind is None:
            ind = self.ind
        if ind > -1:
            self[ind].remove()
            del self[ind]
            if self.ind > 0:
                self.ind -= 1
            else:
                self.ind = None
            self.redraw()
            try:
                self.parent.exp.update()
            except:
                pass

    def rearrange(self, inds):
        if len(inds) == len(self):
            self.ind = inds[self.ind]
            self[:] = [self[i] for i in inds]
            #print([s.filename for s in self])

    def find(self, name):
        """
        Find exposure index by name:
        parameters:
            - name            :  exact name of the exposure

        return: ind
             - ind            :  index of the exposure
        """
        try:
            ind = [s.filename for s in self].index(name)
            return ind
        except:
            NameError('exposure not found')


    def setSpec(self, ind=0, new=False):
        """
        set Spectrum as active (and disactivate other spectra)
        NOTE!!!!: sviewer.s.ind is changed in specClicked() function
        parameter:
            - ind       : index of spectrum to activate 
        """
        ind = ind
        if ind > len(self)-1:
            ind = 0
        if ind < 0:
            ind = len(self) - 1
        #debug(ind)
        #self[ind].specClicked()
        self.parent.s.redraw(ind)
        self.parent.plot.specname.setText(self.parent.s[ind].filename)
        self.parent.plot.e_status = 2
        try:
            self.parent.exp.selectRow(self.ind)
        except:
            pass
        if self.parent.SDSS_filters_status:
            m = max([max(self[self.ind].spec.y())])
            for f in self.parent.sdss_filters:
                f.update(m)

    def normalize(self):
        for i, s in enumerate(self):
            s.normalize()
        self.redraw()

    def prepareFit(self, ind=-1, all=True):
        self.parent.fit.update()
        for s in self:
            s.findFitLines(ind, all=all, debug=False)

    def calcFit(self, ind=-1, recalc=False, redraw=True, timer=False):
        if timer:
            t = Timer()
        for s in self:
            if hasattr(s, 'fit_lines') and len(s.fit_lines) > 0:
                if self.parent.fitType == 'regular':
                    s.calcFit(ind=ind, recalc=recalc, redraw=redraw, tau_limit=self.parent.tau_limit)

                elif self.parent.fitType == 'fft':
                    s.calcFit_fft(ind=ind, recalc=recalc, redraw=redraw, tau_limit=self.parent.tau_limit)

                elif self.parent.fitType == 'fast':
                    s.calcFit_fast(ind=ind, recalc=recalc, redraw=redraw, num_between=self.parent.num_between, tau_limit=self.parent.tau_limit, timer=timer)

            else:
                s.set_fit(x=self[self.ind].spec.raw.x[self[self.ind].cont_mask],
                                       y=np.ones_like(self[self.ind].spec.raw.x[self[self.ind].cont_mask]))
                s.set_gfit()
        if timer:
            t.time('fit ' + self.parent.fitType)

    def calcFitComps(self, recalc=False):
        self.refreshFitComps()
        for s in self:
            if len(s.fit_lines) > 0:
                for sys in self.parent.fit.sys:
                    #print('calcFitComps', sys.ind)
                    if self.parent.fitType == 'regular':
                        s.calcFit(ind=sys.ind, recalc=recalc, tau_limit=self.parent.tau_limit)

                    elif self.parent.fitType == 'fft':
                        s.calcFit_fft(ind=sys.ind, recalc=recalc, tau_limit=self.parent.tau_limit)

                    elif self.parent.fitType == 'fast':
                        s.calcFit_fast(ind=sys.ind, recalc=recalc, num_between=self.parent.num_between, tau_limit=self.parent.tau_limit)

    def reCalcFit(self, ind):
        self.prepareFit(ind=-1)
        self.calcFit(ind=-1)
        if ind != -1:
            self.calcFit(ind=ind)
        self.chi2()

    def refreshFitComps(self):
        for s in self:
            s.construct_fit_comps()

    def redrawFitComps(self):
        if self.ind is not None:
            self[self.ind].redrawFitComps()

    def chi2(self):
        chi2 = np.sum(np.power(self.chi(), 2))
        n = 0
        for s in self:
            if hasattr(s, 'fit_mask') and s.fit_mask is not None:
                n += np.sum(s.fit_mask.x())
        self.parent.chiSquare.setText('  chi2 / dof = {0:.2f} / {1:d}'.format(chi2, int(n - len(self.parent.fit.list_fit()))))
        return chi2

    def chi(self):
        chi = np.asarray([])
        for s in self:
            chi = np.append(chi, s.chi())
        return chi

    def selectCosmics(self):
        for i, s in enumerate(self):
            if i != self.ind:
                s.selectCosmics()
        self[self.ind].selectCosmics()
        
    def calcSmooth(self):
        for i, s in enumerate(self):
            if i != self.ind:
                s.smooth()
        self[self.ind].smooth()
        
    def coscaleExposures_old(self):
        for i, s in enumerate(self):
            if s.sm.n() == 0:
                s.smooth()
        if 1:
            coef = np.nansum(self[self.ind].sm.inter(s.spec.y()))
            for i, s in enumerate(self):
                k = self[self.ind].sm.inter(s.spec.x()) / s.sm.inter(s.spec.x()) #/ coef
                s.spec.raw.y *= k
                s.spec.raw.err *= k
                s.spec.raw.interpolate()
                s.sm.raw.y *= k
                s.sm.raw.interpolate()

        self.redraw()

    def coscaleExposures(self):
        for i, s in enumerate(self):
            if s.sm.n() == 0:
                s.smooth()

        self.coscaleExps(full=True, ind=self.ind)
        self.coscaleExps(full=False)

    def coscaleExps(self, full=True, ind=None):
        for i, si in enumerate(self):
            if ind is None or i == ind:
                mi = np.logical_and(si.spec.y() != 0, si.spec.err() != 0)
                xmin, xmax = np.min(si.spec.x()[mi]), np.max(si.spec.x()[mi])
                for k, sk in enumerate(self):
                    if k != i:
                        c = np.ones_like(sk.spec.y(), dtype=float)
                        mk = np.logical_and(sk.spec.y() != 0, sk.spec.err() != 0)
                        # >>> intersection
                        mask = np.logical_and(mk, np.logical_and(sk.spec.x() > xmin, sk.spec.x() < xmax))
                        if np.sum(mask) > 0:
                            c[mask] = si.sm.inter(sk.spec.x()[mask]) / sk.sm.inter(sk.spec.x()[mask])
                        if full:
                            # >>> left
                            mask = np.logical_and(mk, sk.spec.x() < xmin)
                            if np.sum(mask) > 0:
                                c[mask] = si.sm.inter(xmin) / sk.sm.inter(xmin)
                            # >>> right
                            mask = np.logical_and(mk, sk.spec.x() > xmax)
                            if np.sum(mask) > 0:
                                c[mask] = si.sm.inter(xmax) / sk.sm.inter(xmax)
                        if 1:
                            sk.spec.raw.y *= c
                            sk.spec.raw.err *= c
                            sk.spec.raw.interpolate()
                            sk.sm.raw.y *= c[mk]
                            sk.sm.raw.interpolate(fill_value=(sk.sm.raw.y[0], sk.sm.raw.y[-1]))

        self.redraw()

    def minmax(self):

        minv, maxv = self[0].spec.x()[0], self[0].spec.x()[0]
        for s in self:
            minv = np.min([minv, s.spec.x()[0]])
            maxv = np.max([maxv, s.spec.x()[-1]])
        return minv, maxv

    def apply_regions(self):
        for s in self:
            s.apply_regions()


class gline():
    """
    class for working with lines inside Spectrum plotting
    """

    def __init__(self, x=[], y=[], err=[]):
        self.x = np.asarray(x)
        self.y = np.asarray(y)
        self.err = np.asarray(err)
        # self.x_s, self.y_s, self.err_s = self.x, self.y, self.err
        self.n = self.x.shape[0]
        if self.x.shape != self.y.shape:
            raise IndexError("Dimensions of x and y data are not the same")

    def set_data(self, *args, **kwargs):
        self.delete()
        self.add(*args, **kwargs)

    def add(self, x, y, err=[], axis=0):
        self.x, self.y = np.append(self.x, x), np.append(self.y, y)
        if len(err) > 0:
            self.err = np.append(self.err, err)
        # self.apply_region()
        self.n = len(self.x)

    def delete(self, arg=None, x=None, y=None):
        if arg is None and x is None and y is None:
            self.x = np.array([])
            self.y = np.array([])
        if arg is not None:
            self.x = np.delete(self.x, arg)
            self.y = np.delete(self.y, arg)
        if x is not None:
            arg = np.where(self.x == x)
            self.x = np.delete(self.x, arg)
            self.y = np.delete(self.y, arg)
        if y is not None:
            arg = np.where(self.y == y)
            self.x = np.delete(self.x, arg)
            self.y = np.delete(self.y, arg)
        self.n = len(self.x)

    def interpolate(self, err=False, fill_value=np.NaN):
        if not err:
            self.interpol = interp1d(self.x, self.y, bounds_error=False, fill_value=fill_value, assume_sorted=True)
        else:
            self.err_interpol = interp1d(self.x, self.err, bounds_error=False, fill_value=fill_value, assume_sorted=True)

    def index(self, x):
        return np.searchsorted(self.x, x)

    def f(self, x):
        return self.y[self.index(x)]

    def inter(self, x):
        if not hasattr(self, 'interpol'):
            self.interpolate()
        return self.interpol(x)

    def err_inter(self, x):
        if not hasattr(self, 'err_interpol'):
            self.interpolate(err=True)
        return self.err_interpol(x)

    def sort(self, axis=0):
        try:
            if axis == 0 or axis == 'x':
                args = np.argsort(self.x)
            elif axis == 1 or axis == 'y':
                args = np.argsort(self.y)
        except:
            raise ValueError("Illegal axis argument")
        if len(self.x) > 0:
            self.x = self.x[args]
        if len(self.y) > 0:
            self.y = self.y[args]
        if len(self.err) > 0:
            self.err = self.err[args]

    def find_nearest(self, x=None, y=None):
        if self.n > 0:
            dist = np.zeros_like(self.x)
            if x is not None:
                dist += np.power(self.x - x, 2)
            if y is not None:
                dist += np.power(self.y - y, 2)
            return np.argmin(dist)

    def __str__(self):
        if self.x is not None:
            return 'gline object: ' + '[{0}..{1}]'.format(self.x[0], self.x[-1])
        else:
            return 'empty gline object'

    def __repr__(self):
        st = 'gline: '
        if self.x is not None:
            st += "[{0}..{1}]".format(self.x[0], self.x[-1])
        else:
            return 'empty gline object'
        if self.x is not None:
            st += ", [{0}..{1}]".format(self.y[0], self.y[-1])
        if len(self.err) > 0:
            st += "[{0}..{1}], ".format(self.err[0], self.err[-1])
        return st

    def clean(self, min=None, max=None):
        mask = np.ones_like(self.x, dtype=bool)
        if min is not None:
            mask = np.logical_and(mask, self.y > min)
        if max is not None:
            mask = np.logical_and(mask, self.y < max)
        self.x, self.y, self.err = self.x[mask], self.y[mask], self.err[mask]
        self.n = len(self.x)

    def apply_region(self, regions=[]):
        mask = np.ones_like(self.x_s, dtype=bool)
        if len(regions) > 0:
            regions = np.sort(regions, axis=0)
            for r in regions:
                mask = np.logical_and(mask, np.logical_or(self.x_s < np.min(r), self.x_s > np.max(r)))
        self.x = self.x_s[mask]
        self.y = self.y_s[mask]
        self.err = self.err_s[mask]
        self.n = len(self.x)

        if len(regions) > 0:
            regions = np.sort(regions, axis=0)
            for r in reversed(regions):
                d = abs(r[1] - r[0])
                self.x[self.x > r[1]] -= d

    def convolve(self, resolution=None):
        """
        convolve the line using given resolution
        """
        if resolution is not None:
            m = np.tile(self.x, (len(self.x), 1))
            d = m - np.transpose(m)
            #print(np.exp(-np.power(np.multiply(d, np.transpose(self.x / resolution)), 2) / 2))


class plotStepSpectrum(pg.PlotCurveItem):
    """
    class for plotting step spectrum centered at pixels
    slightly modified from PlotCurveItem
    """
    def generatePath(self, xi, yi, path=True):
        ## each value in the x/y arrays generates 2 points.
        x = xi[:, np.newaxis] + [0,0]
        dx = np.diff(xi) / 2
        dx = np.append(dx, dx[-1])
        x[:, 0] -= dx
        x[:, 1] += dx
        x = x.flatten()
        y = as_strided(yi, shape=[len(yi), 2], strides=[yi.strides[0], 0]).flatten()
        if path:
            path = pg.functions.arrayToQPath(x, y, connect=self.opts['connect'])
            return path
        else:
            return x, y

    def returnPathData(self):
        return self.generatePath(self.xData, self.yData, path=False)


class fitLineProfile(pg.PlotCurveItem):
    def __init__(self, **kwargs):
        super().__init__(kwargs)
        self.setClickable(True)

    def mouseDragEvent(self, ev):

        if QApplication.keyboardModifiers() == Qt.ShiftModifier:
            if ev.button() != Qt.LeftButton:
                ev.ignore()
                return

            if ev.isStart():
                # We are already one step into the drag.
                # Find the point(s) at the mouse cursor when the button was first
                # pressed:
                pos = self.parent.parent.vb.mapSceneToView(ev.pos())
                self.st_pos = pos.x()

            pos = self.parent.parent.vb.mapSceneToView(ev.pos())
            ev.accept()

class specline():
    def __init__(self, parent):
        self.parent = parent
        self.raw = gline()
        self.norm = gline()

    def current(self):
        attr = 'norm' if self.parent.parent.normview else 'raw'
        return getattr(self, attr)

    def x(self):
        return self.current().x

    def y(self):
        return self.current().y

    def err(self):
        return self.current().err

    def f(self, x):
        return self.current().inter(x)

    def n(self):
        return len(self.current().x)

    def index(self, x):
        return self.current().index(x)

    def add(self, x, y=[], err=[]):
        self.raw.add(x=x, y=y, err=err)

    def set(self, x=None, y=None, err=None):
        if x is not None:
            self.current().x = x
        if y is not None:
            self.current().y = y
        if err is not None:
            self.current().err = err

    def interpolate(self):
        self.current().interpolate()

    def normalize(self, norm=True, cont_mask=True, inter=False):
        if cont_mask:
            if norm:
                self.norm.x = self.raw.x[self.parent.cont_mask]
                if len(self.raw.y) > 0:
                    self.norm.y = self.raw.y[self.parent.cont_mask] / self.parent.cont.y
                if len(self.raw.err) > 0:
                        self.norm.err = self.raw.err[self.parent.cont_mask] / self.parent.cont.y
                self.norm.n = len(self.norm.x)
            else:
                self.raw.x[self.parent.cont_mask] = self.norm.x
                if len(self.raw.y) > 0:
                    self.raw.y[self.parent.cont_mask] = self.norm.y * self.parent.cont.y
                if len(self.raw.err) > 0:
                    self.raw.err[self.parent.cont_mask] = self.norm.err * self.parent.cont.y
        else:
            if (norm and len(self.raw.y)>0) or (not norm and len(self.norm.y)>0):
                if not inter:
                    cont = self.parent.cont.y
                else:
                    self.parent.cont.interpolate()
                    if norm:
                        cont = self.parent.cont.inter(self.raw.x)
                    else:
                        cont = self.parent.cont.inter(self.norm.x)
            if norm:
                self.norm.x = self.raw.x[:]
                if len(self.raw.y) > 0:
                    self.norm.y = self.raw.y / cont
                self.norm.n = len(self.norm.x)
            else:
                self.raw.x = self.norm.x[:]
                if len(self.norm.y) > 0:
                    self.raw.y = self.norm.y * cont

    def inter(self, x):
        return self.current().inter(x)

class image():
    """
    class for working with images (2d spectra) inside Spectrum plotting
    """
    def __init__(self, x=None, y=None, z=None, err=None, mask=None):
        if any([v is not None for v in [x, y, z, err, mask]]):
            self.set_data(x=x, y=y, z=z, err=err, mask=mask)
        else:
            self.z = None

    def set_data(self, x=None, y=None, z=None, err=None, mask=None):
        for attr, val in zip(['z', 'err', 'mask'], [z, err, mask]):
            if val is not None:
                setattr(self, attr, np.asarray(val))
            else:
                setattr(self, attr, val)
        if x is not None:
            self.x = np.asarray(x)
        else:
            self.x = np.arange(z.shape[0])
        if y is not None:
            self.y = np.asarray(y)
        else:
            self.y = np.arange(z.shape[1])

        self.pos = [self.x[0] - (self.x[1] - self.x[0]) / 2, self.y[0] - (self.y[1] - self.y[0]) / 2]
        self.scale = [(self.x[-1] - self.x[0]) / (self.x.shape[0]-1), (self.y[-1] - self.y[0]) / (self.y.shape[0]-1)]
        #self.mask = np.zeros_like(self.z)
        self.getQuantile()
        self.setLevels(self.quantile[0], self.quantile[1])

    def getQuantile(self, quantile=0.997):
        if self.z is not None:
            x = np.sort(self.z.flatten())
            x = x[~np.isnan(x)]
            self.quantile = [x[int(len(x)*(1-quantile)/2)], x[int(len(x)*(1+quantile)/2)]]
        else:
            self.quantile = [0, 1]

    def setLevels(self, bottom, top):
        top, bottom = np.max([top, bottom]), np.min([top, bottom])
        if top - bottom < (self.quantile[1] - self.quantile[0]) / 100:
            top += ((self.quantile[1] - self.quantile[0]) / 100 - (top - bottom)) /2
            bottom -= ((self.quantile[1] - self.quantile[0]) / 100 - (top - bottom)) / 2
        #top = np.max([np.min([top, self.quantile[1]]), self.quantile[0]])
        #bottom = np.max([np.min([bottom, self.quantile[1]]), self.quantile[0]])
        self.levels = [bottom, top]

    def find_nearest(self, x, y):
        if len(self.z.shape) == 2:
            return self.z[np.min([self.z.shape[0]-1, (np.abs(self.y - y)).argmin()]), np.min([self.z.shape[1]-1, (np.abs(self.x - x)).argmin()])]
        else:
            return None

    def collapse(self, axis='x', rect=None):
        if rect is None:
            rect = [[self.x[0], self.x[-1]], [self.y[0], self.y[-1]]]
        self.y_imin, self.y_imax = np.searchsorted(self.y, rect[1][0]), np.searchsorted(self.y, rect[1][1])
        self.x_imin, self.x_imax = np.searchsorted(self.x, rect[0][0]), np.searchsorted(self.x, rect[0][1])
        s_axis = 'y' if axis == 'x' else 'x'
        ind = 1 if axis == 'x' else 0
        return getattr(self, s_axis)[getattr(self, s_axis + '_imin'):getattr(self, s_axis + '_imax')], \
               np.sum(self.z[self.y_imin:self.y_imax, self.x_imin:self.x_imax], axis=ind)

    def add_mask(self, rect=None, add=True):
        if self.mask is None:
            self.mask = np.zeros_like(self.z)
        if rect is not None:
            x1, x2 = (np.abs(self.x - rect[0][0])).argmin(), (np.abs(self.x - rect[0][1])).argmin()
            y1, y2 = (np.abs(self.y - rect[1][0])).argmin(), (np.abs(self.y - rect[1][1])).argmin()
            self.mask[y1:y2+1, x1:x2+1] = int(add)

class spec2d():
    def __init__(self, parent):
        self.parent = parent
        self.raw = image()
        self.cr = None
        self.sky = None
        self.slits = []
        self.gslits = []
        self.trace = None
        self.trace_width = [None, None]
        self.moffat = moffat_func()

    def set(self, x=None, y=None, z=None, err=None, mask=None):
        self.raw.set_data(x=x, y=y, z=z, err=err, mask=mask)

    def set_image(self, name, colormap):
        image = pg.ImageItem()
        if name == 'raw':
            image.setImage(self.raw.z.T)
        elif name == 'err':
            image.setImage(self.raw.err.T)
        elif name == 'mask':
            image.setImage(self.raw.mask.T)
        elif name == 'cr':
            image.setImage(self.cr.mask.T)
        elif name == 'sky':
            image.setImage(self.sky.z.T)
        image.translate(self.raw.pos[0], self.raw.pos[1])
        image.scale(self.raw.scale[0], self.raw.scale[1])
        image.setLookupTable(colormap)
        #image.setLevels(self.raw.levels)
        return image

    def cr_remove(self, update, **kwargs):
        if self.cr is None:
            self.cr = image(x=self.raw.x, y=self.raw.y, mask=np.zeros_like(self.raw.z))
        z = self.raw.z
        z = np.insert(z, 0, z[:4], axis=0)
        z = np.insert(z, z.shape[0], z[-4:], axis=0)
        z, mask = cosmicray_lacosmic(z, **kwargs)
        if update == 'new':
            self.cr.mask = mask[4:-4]
        if update == 'add':
            self.cr.mask = np.logical_or(self.cr.mask, mask[4:-4])
        print(update, np.sum(self.cr.mask.flatten()))

    def expand_mask(self, exp_pixel=1):
        m = np.copy(self.cr.mask)
        for p in itertools.product(np.linspace(-exp_pixel, exp_pixel, 2*exp_pixel+1).astype(int), repeat=2):
            m1 = np.copy(self.cr.mask)
            if p[0] < 0:
                m1 = np.insert(m1[:p[0],:], [0]*np.abs(p[0]), 0, axis=0)
            if p[0] > 0:
                m1 = np.insert(m1[p[0]:, :], [m1.shape[0]-p[0]]*p[0], 0, axis=0)
            if p[1] < 0:
                m1 = np.insert(m1[:,:p[1]], [0]*np.abs(p[1]), 0, axis=1)
            if p[1] > 0:
                m1 = np.insert(m1[:, p[1]:], [m1.shape[1]-p[1]]*p[1], 0, axis=1)
            m = np.logical_or(m, m1)
        self.cr.mask = m

    def intelExpand(self, exp_factor=0.5):
        z_saved, mask_saved = np.copy(self.raw.z), np.copy(self.cr.mask)
        self.expand_mask()
        self.extrapolate(inplace=True)
        self.cr.mask = np.logical_or(mask_saved, np.logical_and(np.abs(self.raw.z / z_saved - 1) > exp_factor, self.cr.mask))
        if 1:
            self.parent.parent.s.append(Spectrum(self.parent.parent, 'delta'))
            self.parent.parent.s[-1].spec2d.set(x=self.raw.x, y=self.raw.y, z=self.raw.z / z_saved - 1)
            self.parent.parent.s[-1].spec2d.raw.setLevels(-exp_factor, exp_factor)
        self.raw.z = z_saved

    def extrapolate(self, inplace=False, extr_width=1, extr_height=1):
        z = np.copy(self.raw.z)
        z[self.cr.mask] = np.nan
        kernel = Gaussian2DKernel(x_stddev=extr_width, y_stddev=extr_height)
        z = convolve(z, kernel)
        z1 = np.copy(self.raw.z)
        self.cr.mask = self.cr.mask.astype(bool)
        z1[self.cr.mask] = z[self.cr.mask]
        if not inplace:
            self.parent.parent.s.append(Spectrum(self.parent.parent, 'CR_removed'))
            self.parent.parent.s[-1].spec2d.set(x=self.raw.x, y=self.raw.y, z=z1)
        else:
            self.raw.z = z1

    def moffat_fit_integ(self, x, a, x_0, gamma, c):
        dx = np.median(np.diff(x)) / 2
        x = np.append(x - dx, x[-1] + dx)
        y = self.moffat.cdf(x, loc=x_0, scale=gamma)

        return a * np.diff(y) + c

    def profile(self, xmin, xmax, ymin, ymax, x_0=None, slit=None, plot=False):
        x, y = self.raw.collapse(rect=[[xmin, xmax], [ymin, ymax]])
        if x_0 is None:
            x_0 = x[np.argmax(y)]
        c = np.median(np.append(y[:int(len(y) / 4)], y[int(3 * len(y) / 4)]))
        if slit is None:
            gamma = 2.35482 * np.std((y - c) * x) / np.std(y - c) / 2 / np.sqrt(2 ** (1 / 4.765) - 1)
        else:
            gamma = 2.35482 * slit / 2 / np.sqrt(2 ** (1 / 4.765) - 1)
        a = np.max(y) - c


        if plot:
            try:
                plt.close()
            except:
                pass
            fig, ax = plt.subplots()
            ax.plot(x, y, '-r')

        popt, pcov = curve_fit(self.moffat_fit_integ, x, y, p0=[a, x_0, gamma, c])

        pos, fwhm = self.raw.x[np.searchsorted(self.raw.x, (xmin+xmax)/2)], Moffat1D(popt[0], popt[1], popt[2], 4.765).fwhm
        if slit is None or (np.abs(popt[1] - x_0) < slit / 3 and np.abs(fwhm / slit - 1) < 0.3):
            self.slits.append([pos, np.min([np.max([popt[1], x[0]]), x[-1]]), fwhm])

        if plot:
            ax.plot(x, self.moffat_fit_integ(x, popt[0], popt[1], popt[2], popt[3]), '-b')
            ax.set_title('FWHM = {0:.2f}, center={1:.2f}'.format(fwhm, x_0))
            plt.show()
            self.parent.parent.s.redraw()

    def addSlits(self):
        for s in self.slits:
            self.gslits.append([pg.ErrorBarItem(x=np.asarray([s[0]]), y=np.asarray([s[1]]),
                                                top=np.asarray([s[2]]) / 2, bottom=np.asarray([s[2]]) / 2,
                                                pen=pg.mkPen('c', width=2), beam=4),
                                pg.ScatterPlotItem(x=np.asarray([s[0]]), y=np.asarray([s[1]]),
                                                   pen=pg.mkPen('k', width=0.5), brush=pg.mkBrush('c'))])
            self.parent.parent.spec2dPanel.vb.addItem(self.gslits[-1][0])
            self.parent.parent.spec2dPanel.vb.addItem(self.gslits[-1][1])

    def fit_trace(self, shape='poly'):
        pos, trace, width = np.transpose(np.asarray(self.slits))
        if shape == 'poly':
            p = np.polyfit(pos, trace, 3)
            trace_pos = np.polyval(p, self.parent.cont2d.x)
            p = np.polyfit(pos, width, 3)
            trace_width = np.polyval(p, self.parent.cont2d.x)
        elif shape == 'power':
            x1, x2, y1, y2 = pos[0], pos[-1], trace[0], trace[-1]
            powerlaw = lambda x, amp, index, c: amp * (x ** index) + c
            popt, pcov = curve_fit(powerlaw, p0=(x2 * (y2 - y1) / (x1 - x2), -1, (y1*x1 - y2*x2)/(x1-x2)))
            self.trace_pos = powerlaw(self.parent.cont2d.x, popt[0], popt[1], popt[2])
        if 0:
            self.parent.s.redraw()
        else:
            self.trace = [self.parent.cont2d.x[:], trace_pos, trace_width]

    def set_trace(self):
        self.trace_pos = pg.PlotCurveItem(x=self.trace[0], y=self.trace[1], pen=pg.mkPen(255, 255, 255, width=3))
        self.parent.parent.spec2dPanel.vb.addItem(self.trace_pos)
        self.trace_width = pg.PlotCurveItem(x=np.concatenate((self.trace[0], np.array([np.inf]), self.trace[0])),
                                            y=np.concatenate((self.trace[1] + self.trace[2] / 2, np.array([np.inf]), self.trace[1] - self.trace[2] / 2)),
                                            connect="finite", pen=pg.mkPen(255, 255, 255, width=3, style=Qt.DashLine))
        self.parent.parent.spec2dPanel.vb.addItem(self.trace_width)

    def sky_model(self, xmin, xmax, border=0, slit=None, mask_type='moffat', model='median', window=0, smooth=0, inplace=True, plot=0):

        if self.sky is None or not inplace:
            self.sky = image(x=self.raw.x, y=self.raw.y, z=np.zeros_like(self.raw.z), mask=np.zeros_like(self.raw.z))
        if self.trace is not None:
            inds = np.searchsorted(self.raw.x, self.trace[0][(self.trace[0] >= xmin) * (self.trace[0] <= xmax)])
        elif slit is not None:
            inds = np.where(np.logical_and(self.parent.cont_mask2d, np.logical_and(self.raw.x >= xmin, self.raw.x <= xmax)))[0]
        else:
            inds = []
        for k, i in enumerate(inds):
            print(i)
            if mask_type == 'moffat':
                if self.trace is None and slit is not None:
                    x_0, gamma = self.parent.cont2d.y[k], self.extr_slit / 2 / np.sqrt(2 ** (1 / 4.765) - 1)
                else:
                    x_0 = self.trace[1][k]
                    gamma = (self.trace[2][k] - x_0) * 2 / 2 / np.sqrt(2 ** (1 / 4.765) - 1)
                m = self.moffat.ppf([0.05, 0.95], loc=x_0, scale=gamma)
                mask_sky = np.logical_or(self.raw.y < m[0], self.raw.y > m[1])
            elif slit is not None:
                mask_sky = 1 / (np.exp(-40 * (np.abs(self.raw.y - self.parent.cont2d.y[k]) - slit * 2)) + 1)
            mask_sky[:border] = 0
            mask_sky[-border:] = 0
            mask_reg = np.zeros_like(self.raw.mask, dtype=bool)
            mask_reg[:, i - window:i + window + 1] = True
            mask = np.logical_and(np.logical_not(self.cr.mask), mask_reg * mask_sky[:, np.newaxis])
            self.sky.mask[:, i] = mask[:, i]
            if window > 0:
                y = np.mean(self.raw.z[mask], axis=0)
            else:
                y = self.raw.z[mask]

            if model == 'median':
                sky = np.median(y) * np.ones_like(self.raw.y)
            elif model == 'mean':
                sky = np.mean(y) * np.ones_like(self.raw.y)
            elif model == 'fit':
                p = np.polyfit(self.raw.y[mask[:,i]], y, 2)
                sky = np.polyval(p, self.raw.y)
                if plot:
                    fig, ax = plt.subplots()
                    ax.plot(self.raw.y[mask[:,i]], y, 'ok')
                    ax.plot(self.raw.y, sky, '-r')
                    plt.show()
                #def fun(x, t, y):
                #    return x[0] * np.exp(-x[1] * t) * np.sin(x[2] * t) - y
                #res_robust = least_squares(fun, x0, loss='soft_l1', f_scale=0.1, args=(t_train, y_train))

            self.sky.z[:,i] = sky

        if smooth > 0:
            sk = np.asarray(sk)
            from scipy.signal import savgol_filter
            fig, ax = plt.subplots()
            ax.plot(s.spec2d.raw.x[s.cont_mask2d], sk)
            mask = np.ones_like(sk, dtype=bool)
            for i in range(3):
                y = savgol_filter(sk[mask], 101, 5)
                ax.plot(s.spec2d.raw.x[s.cont_mask2d][mask], y, '--r')

                mask[mask] = np.logical_and((sk[mask] / y - 1) < 0.3, mask[mask])

                # y, lmbd = smooth_data(data[0], data[1], d=4, stdev=1e-4)

            sky = sk[:]
            sky[mask] = savgol_filter(sk[mask], 21, 5)

    def extract(self, xmin, xmax, slit=None, mask_type='moffat', helio=None, airvac=True, inplace=False):

        if self.trace is not None:
            inds = np.searchsorted(self.raw.x, self.trace[0][(self.trace[0] >= xmin) * (self.trace[0] <= xmax)])
        elif slit is not None:
            inds = np.where(np.logical_and(self.parent.cont_mask2d, np.logical_and(self.raw.x >= xmin, self.raw.x <= xmax)))[0]
        else:
            inds = []
        y, err = [], []
        for k, i in enumerate(inds):
            print(k,i)
            if mask_type == 'moffat':
                if self.trace is None and slit is not None:
                    x_0, gamma = self.parent.cont2d.y[k], self.extr_slit / 2 / np.sqrt(2 ** (1 / 4.765) - 1)
                else:
                    x_0 = self.trace[1][k]
                    gamma = (self.trace[2][k] - x_0) * 2 / 2 / np.sqrt(2 ** (1 / 4.765) - 1)
                profile = self.moffat_fit_integ(self.raw.y, 1, x_0=x_0, gamma=gamma, c=0)
            elif mask_type == 'rectangular':
                profile = 1 / (np.exp(-40 * (np.abs(self.raw.y - self.parent.cont2d.y[k]) - self.extr_slit)) + 1)
            elif mask_type == 'gaussian':
                profile = np.exp(-(np.abs(self.raw.y - self.parent.cont2d.y[k]) / self.extr_slit / 2.35482) ** 2)

            v = np.sum((1 - self.cr.mask[:, i]) * profile**2 / self.raw.err[:, i])
            flux = np.sum((self.raw.z[:, i] - self.sky.z[:, i]) * profile / self.raw.err[:, i] * (1 - self.cr.mask[:, i]))

            y.append(flux / v)
            err.append(np.sum((1 - self.cr.mask[:, i]) * profile) / v)

        print(y, err)
        if inplace:
            pass
        else:
            print(self.raw.x[inds], np.asarray(y), np.asarray(err))
            self.parent.parent.s.append(Spectrum(self.parent.parent, 'extracted', data=[self.raw.x[inds], np.asarray(y),
                                                                          np.asarray(err)]))
            if helio is not None:
                self.parent.parent.s[-1].helio_vel = helio
                self.parent.parent.s[-1].apply_shift(helio)

            if airvac:
                self.parent.parent.s[-1].airvac()
            self.parent.parent.s[-1].spec2d.set(x=self.parent.parent.s[-1].spec.x(), y=self.raw.y,
                                         z=self.raw.z[:, inds] - self.sky.z[:, inds])

class Spectrum():
    """
    class for plotting Spectrum with interactive functions
    """
    def __init__(self, parent, name=None, data=None, resolution=0):
        self.parent = parent
        self.filename = name
        self.resolution = resolution
        self.date = ''
        self.wavelmin = None
        self.wavelmax = None
        self.init_pen()
        self.spec = specline(self)
        self.mask = specline(self)
        self.bad_mask = specline(self)
        self.fit_mask = specline(self)
        self.cont = gline()
        self.cont2d = gline()
        self.spline = gline()
        self.spline2d = gline()
        self.cont_mask = None
        self.cont_mask2d = None
        #self.norm = gline()
        self.sm = specline(self)
        self.rebin = None
        self.fit = specline(self)
        self.fit_comp = []
        self.cheb = specline(self)
        self.res = gline()
        self.kde = gline()
        self.parent.plot.specname.setText(self.filename)
        self.view = 'step'
        self.parent.s.ind = len(self.parent.s)
        if data is not None:
            self.set_data(data)
            self.parent.s.ind = len(self.parent.s)-1
            self.init_GU()
        self.spec2d = spec2d(self)
        self.mask2d = None
        self.cr_mask2d = None
        self.err2d = None
        self.sky2d = None

    def init_pen(self):
        self.err_pen = pg.mkPen(70, 130, 180)
        self.cont_pen = pg.mkPen(168, 66, 195, width=3)
        self.fit_pen = pg.mkPen(255, 69, 0, width=4)
        self.fit_comp_pen = pg.mkPen(255, 215, 63, width=1.0)
        self.spline_brush = pg.mkBrush(0, 191, 255, 255) # pg.mkBrush(117, 218, 50, 255)

    def ind(self):
        return self.parent.s.index(self)

    def active(self):
        return self == self.parent.s[self.parent.s.ind]

    def init_GU(self):
        #print('caller name:', inspect.stack()[1][3], inspect.stack()[2][3], inspect.stack()[3][3], inspect.stack()[4][3])
        if self.active():
            self.view = self.parent.specview
            self.pen = pg.mkPen(255, 255, 255)
            self.points_brush = pg.mkBrush(145, 224, 29)
            self.points_size = 15
            self.sm_pen = pg.mkPen(245, 0, 80)
            self.bad_brush = pg.mkBrush(252, 58, 38)
            self.region_brush = pg.mkBrush(147, 185, 69, 60)
            cdict = get_cmap('viridis')
            cmap = np.array(cdict.colors)
            #cmap[0] = [1,1,1]
            cmap[-1] = [1,0.4,0]
            map = pg.ColorMap(np.linspace(0,1,cdict.N), cmap, mode='rgb')
            self.colormap = map.getLookupTable(0.0, 1.0, 256, alpha=False)
            map = pg.ColorMap(np.linspace(0, 1, 2), [[0.0, 0.0, 0.0, 1.0], [0.0, 0.0, 0.0, 0.0]], mode='rgb')
            self.maskcolormap = map.getLookupTable(1.0, 0.0, 2, alpha=True)
            map = pg.ColorMap(np.linspace(0, 1, 2), [[1.0, 1.0, 1.0, 1.0], [0.0, 0.0, 0.0, 0.0]], mode='rgb')
            self.cr_maskcolormap = map.getLookupTable(1.0, 0.0, 2, alpha=True)
        else:
            if self.parent.showinactive:
                self.view = self.parent.specview.replace('err', '')
                self.pen = pg.mkPen(100, 100, 100)
                self.points_brush = pg.mkBrush(81, 122, 136)
                self.points_size = 8 if self.parent.normview else 3
                self.sm_pen = pg.mkPen(105, 30, 30, style=Qt.DashLine)
                self.bad_brush = pg.mkBrush(252, 58, 38, 10)
                self.region_brush = pg.mkBrush(92, 132, 232, 40)
            else:
                return None

        # >>> plot spectrum
        if len(self.spec.x()) > 0:
            x, y, err = self.spec.x(), self.spec.y(), self.spec.err()

            if 'err' in self.view and len(err) == len(y):
                self.g_err = pg.ErrorBarItem(x=x, y=y, top=err, pen=self.err_pen, bottom=err, beam=(x[1]-x[0])/2)
                self.parent.vb.addItem(self.g_err)
            if 'point' in self.view:
                self.g_point = pg.ScatterPlotItem(x=x, y=y, size=10, brush=pg.mkBrush(52, 152, 219, 255))
                self.parent.vb.addItem(self.g_point)
            if 'step' in self.view:
                self.g_line = plotStepSpectrum(x=x, y=y, clickable=True)
                self.g_line.setPen(self.pen)
                self.g_line.sigClicked.connect(self.specClicked)
                self.parent.vb.addItem(self.g_line)
            if 'line' in self.view:
                self.g_line = pg.PlotCurveItem(x=x, y=y, clickable=True)
                self.g_line.sigClicked.connect(self.specClicked)
                self.g_line.setPen(self.pen)
                self.parent.vb.addItem(self.g_line)

        # >>> plot fit point:
        self.set_fit_mask()
        if len(self.fit_mask.x()) > 0:
            if self.parent.selectview == 'point':
                self.points = pg.ScatterPlotItem(x=self.spec.x()[self.fit_mask.x()], y=self.spec.y()[self.fit_mask.x()], size=self.points_size, brush=self.points_brush)
                self.parent.vb.addItem(self.points)

            elif self.parent.selectview == 'color':
                x, y = np.copy(self.spec.x()), np.copy(self.spec.y())
                if len(x) > 0:
                    y[np.logical_not(self.fit_mask.x())] = np.NaN
                if 'line' in self.parent.specview:
                    self.points = pg.PlotCurveItem(connect='finite', pen=pg.mkPen((145, 180, 29), width=5))
                else:
                    self.points = plotStepSpectrum(connect='finite', pen=pg.mkPen((145, 180, 29), width=5))
                self.points.setData(x=x, y=y)
                self.parent.vb.addItem(self.points)

            elif self.parent.selectview == 'region':
                self.updateRegions()

        # >>> plot bad point:
        if len(self.bad_mask.x()) > 0 and len(self.spec.x()) > 0:
            self.bad_pixels = pg.ScatterPlotItem(x=self.spec.x()[self.bad_mask.x()], y=self.spec.y()[self.bad_mask.x()],
                                                 size=30, symbol='d', brush=self.bad_brush)
            self.parent.vb.addItem(self.bad_pixels)

        # >>> plot fit:
        if self.parent.fitPoints:
            self.g_fit = pg.ScatterPlotItem(x=[], y=[], size=5, symbol='o',
                                            pen=self.fit_pen, brush=pg.mkBrush(self.fit_pen.color()))
        else:
            self.g_fit = pg.PlotCurveItem(x=[], y=[], pen=self.fit_pen)
        self.parent.vb.addItem(self.g_fit)
        self.set_gfit()
        if len(self.parent.fit.sys) > 0:
            self.construct_g_fit_comps()

        if self.parent.normview:
            self.normline = pg.InfiniteLine(pos=1, angle=0, pen=pg.mkPen(color=self.cont_pen.color(), style=Qt.DashLine))
            self.parent.vb.addItem(self.normline)
        else:
            if len(self.parent.s) == 0 or self.active():
                self.g_cont = pg.PlotCurveItem(x=self.cont.x, y=self.cont.y, pen=self.cont_pen)
                self.parent.vb.addItem(self.g_cont)
                self.g_spline = pg.ScatterPlotItem(x=self.spline.x, y=self.spline.y, size=12, symbol='s',
                                                   pen=pg.mkPen(0, 0, 0, 255), brush=self.spline_brush)
                self.parent.vb.addItem(self.g_spline)

        # >>> plot chebyshev continuum:
        self.g_cheb = pg.PlotCurveItem(x=[], y=[], pen=pg.mkPen(color=self.cont_pen.color(), style=Qt.DashLine, width=3))
        self.parent.vb.addItem(self.g_cheb)

        if self.parent.fit.cont_fit:
            self.set_cheb()

        # >>> plot smooth of spectrum:
        if self.sm.n() > 0:
            self.sm_line = pg.PlotCurveItem(x=self.sm.x(), y=self.sm.y(), pen=self.sm_pen)
            self.parent.vb.addItem(self.sm_line)

        # >>> plot residuals:
        if self.parent.show_residuals and (len(self.parent.s) == 0 or self.active()):
            self.residuals = pg.ScatterPlotItem(x=self.res.x, y=self.res.y, size=10,
                                                brush=pg.mkBrush(52, 152, 219, 255))
            self.parent.residualsPanel.vb.addItem(self.residuals)
            self.kde_line = pg.PlotCurveItem(x=-self.kde.x, y=self.kde.y, pen=pg.mkPen(52, 152, 219, 255), fillLevel=0,
                                             brush=pg.mkBrush(52, 152, 219, 100))
            self.kde_line.rotate(270)
            self.parent.residualsPanel.kde.addItem(self.kde_line)
            self.kde_local = pg.PlotCurveItem(x=-self.kde.x, y=self.kde.y, pen=pg.mkPen(46, 204, 113, 255))
            self.kde_local.rotate(270)
            self.parent.residualsPanel.kde.addItem(self.kde_local)
            x = np.linspace(-3, 3, 100)
            y = 1 / np.sqrt(2 * np.pi) * np.exp(-x ** 2 / 2)
            self.kde_gauss = pg.PlotCurveItem(x=x, y=y, pen=pg.mkPen(252, 52, 19, 255))
            self.kde_gauss.rotate(270)
            self.parent.residualsPanel.kde.addItem(self.kde_gauss)

        # >>> plot 2d spectrum:
        if self.parent.show_2d and (len(self.parent.s) == 0 or self.active()):
            if self.spec2d.raw.z is not None and self.spec2d.raw.z.shape[0] > 0 and self.spec2d.raw.z.shape[1] > 0:
                self.image2d = self.spec2d.set_image('raw', self.colormap)
                self.image2d.setLevels(self.spec2d.raw.levels)
                self.parent.spec2dPanel.vb.addItem(self.image2d)
                self.parent.spec2dPanel.vb.removeItem(self.parent.spec2dPanel.cursorpos)
                self.parent.spec2dPanel.vb.addItem(self.parent.spec2dPanel.cursorpos, ignoreBounds=True)
                if self.spec2d.raw.err is not None:
                    self.err2d = self.spec2d.set_image('err', self.colormap)
                if self.spec2d.raw.mask is not None:
                    self.mask2d = self.spec2d.set_image('mask', self.maskcolormap)
                if self.spec2d.cr is not None and self.spec2d.cr.mask is not None:
                    self.cr_mask2d = self.spec2d.set_image('cr', self.cr_maskcolormap)
                    self.parent.spec2dPanel.vb.addItem(self.cr_mask2d)
                if self.spec2d.trace is not None:
                    self.spec2d.set_trace()
                if len(self.spec2d.slits) > 0:
                    self.spec2d.addSlits()
                if self.spec2d.sky is not None:
                    self.sky2d = self.spec2d.set_image('sky', self.colormap)
            if len(self.parent.s) == 0 or self.active():
                self.g_cont2d = pg.PlotCurveItem(x=self.cont2d.x, y=self.cont2d.y, pen=self.cont_pen)
                self.parent.spec2dPanel.vb.addItem(self.g_cont2d)
                self.g_spline2d = pg.ScatterPlotItem(x=self.spline2d.x, y=self.spline2d.y, size=12, symbol='s',
                                                   pen=pg.mkPen(0, 0, 0, 255), brush=self.spline_brush)
                self.parent.spec2dPanel.vb.addItem(self.g_spline2d)

    def remove(self):
        try:
            if 'err' in self.view:
                try:
                    self.parent.vb.removeItem(self.g_err)
                except:
                    pass
            if 'point' in self.view:
                self.parent.vb.removeItem(self.g_point)
            if 'step' in self.view:
                self.parent.vb.removeItem(self.g_line)
            if 'line' in self.view:
                self.parent.vb.removeItem(self.g_line)
        except:
            pass
        try:
            self.remove_g_fit_comps()
        except:
            pass
        attrs = ['g_fit', 'g_fit_comp', 'points', 'bad_pixels', 'g_cont', 'g_spline',
                 'normline', 'sm_line', 'g_cheb', 'rebin']
        for attr in attrs:
            try:
                self.parent.vb.removeItem(getattr(self, attr))
            except:
                pass
        try:
            if self.parent.selectview == 'region':
                for r in self.regions:
                    self.parent.vb.removeItem(r)
        except:
            pass


        try:
            self.parent.residualsPanel.vb.removeItem(self.residuals)
        except:
            pass
        try:
            self.parent.residualsPanel.kde.removeItem(self.kde_line)
            self.parent.residualsPanel.kde.removeItem(self.kde_gauss)
            self.parent.residualsPanel.kde.removeItem(self.kde_local)
        except:
            pass

        attrs = ['image2d', 'mask2d', 'g_cont2d', 'g_spline2d', 'trace_pos', 'trace_width']
        for attr in attrs:
            try:
                self.parent.spec2dPanel.vb.removeItem(getattr(self, attr))
            except:
                pass

        for g in self.spec2d.gslits:
            try:
                self.parent.spec2dPanel.vb.removeItem(g[0])
                self.parent.spec2dPanel.vb.removeItem(g[1])
            except:
                pass

    def redraw(self):
        self.remove()
        self.init_GU()
        try:
            self.parent.abs.redraw()
        except:
            pass
        self.set_res()

    def set_data(self, data=None):
        if data is not None:
            if len(data) >= 3:
                print(data[1], data[2])
                mask = np.logical_and(data[1] != 0, data[2] != 0)
                print(len(data[0]), np.sum(mask))
                self.spec.add(data[0][mask], data[1][mask], err=data[2][mask])
                if len(data) == 4:
                    self.cont.set_data(data[0][mask], data[3][mask])
                    self.cont_mask = np.ones_like(self.spec.x(), dtype=bool)
            elif len(data) == 2:
                mask = (data[1] != 0)
                self.spec.add(data[0][mask], data[1][mask])
            else:
                mask = data[1] != np.NaN
        print(len(self.spec.raw.x), len(self.spec.raw.y))
        self.spec.raw.interpolate()
        self.wavelmin, self.wavelmax = self.spec.raw.x[0], self.spec.raw.x[-1]
        self.mask.set(x=np.zeros_like(self.spec.raw.x, dtype=bool))
        self.bad_mask.set(x=np.isnan(self.spec.raw.y))
        self.set_res()

    def update_fit(self):
        if len(self.fit.norm.x) > 0 and self.cont.n > 0 and self.active():
            self.set_gfit()
            self.set_res()
            if self.parent.fit.cont_fit:
                self.set_cheb()
            self.parent.s.chi2()

    def set_fit(self, x, y):
        if self.cont.n > 0: # and self.active():
            self.fit.norm.set_data(x=x, y=y)
            self.fit.norm.interpolate()
            if not self.parent.normview:
                self.fit.normalize(norm=False, cont_mask=False, inter=True)
                self.fit.raw.interpolate()

    def set_gfit(self):
        if len(self.fit.norm.x) > 0 and self.cont.n > 0 and self.active():
            self.g_fit.setData(self.fit.x(), self.fit.y())

    def construct_fit_comps(self):
        self.fit_comp = []
        for sys in self.parent.fit.sys:
            self.fit_comp.append(specline(self))
        if self.active():
            self.remove_g_fit_comps()
            self.construct_g_fit_comps()

    def set_fit_comp(self, x, y, ind=-1):
        for i in range(len(self.fit_comp)):
            if ind == i or ind == -1:
                self.fit_comp[i].norm.set_data(x=x, y=y)
                if not self.parent.normview:
                    self.fit_comp[i].normalize(norm=False, cont_mask=False, inter=True)
                if self.active():
                    if self.parent.comp_view == 'one' and self.parent.comp == i or self.parent.comp_view == 'all':
                        ind = i if self.parent.comp_view == 'all' else 0
                        self.g_fit_comp[ind].setData(x=self.fit_comp[i].x(), y=self.fit_comp[i].y())

    def construct_g_fit_comps(self):
        if self.active():
            self.g_fit_comp = []
            for i, c in enumerate(self.fit_comp):
                if self.parent.comp_view == 'one' and self.parent.comp == i or self.parent.comp_view == 'all':
                    style = Qt.DashLine if self.parent.comp_view == 'all' and self.parent.comp != i else Qt.SolidLine
                    color = pg.mkPen(50, 115, 235, width=1.0) if self.parent.comp_view == 'all' and self.parent.comp != i else self.fit_comp_pen.color()
                    pen = color = pg.mkPen(50, 115, 235, width=1.0) if self.parent.comp_view == 'all' and self.parent.comp != i else self.fit_comp_pen
                    self.g_fit_comp.append(pg.PlotCurveItem(x=c.x(), y=c.y(), pen=pen)) #pg.mkPen(color=color, style=style)))
                    self.parent.vb.addItem(self.g_fit_comp[-1])

    def remove_g_fit_comps(self):
        try:
            for g in self.g_fit_comp:
                try:
                    self.parent.vb.removeItem(g)
                except:
                    pass
        except:
            pass

    def redrawFitComps(self):
        if self.active():
            self.remove_g_fit_comps()
            self.construct_g_fit_comps()

    def set_cheb(self, x=None, y=None):
        if self.active():
            if x is None and y is None:
                self.cheb.norm.set_data(x=self.spec.norm.x, y=self.correctContinuum(self.spec.norm.x))
                self.cheb.normalize(norm=False, cont_mask=False)
            else:
                self.cheb.set(x=x, y=y)
            self.g_cheb.setData(x=self.cheb.x(), y=self.cheb.y())

    def set_res(self):
        if 1 and hasattr(self.parent, 'residualsPanel') and self.parent.s.ind < len(self.parent.s) and self.active() and len(self.fit.x()) > 0:
            self.res.x = self.spec.x()[self.fit_mask.x()]
            self.res.y = (self.spec.y()[self.fit_mask.x()] - self.fit.f(self.spec.x()[self.fit_mask.x()])) / self.spec.err()[self.fit_mask.x()]
            self.residuals.setData(x=self.res.x, y=self.res.y)
            if len(self.res.y) > 1 and not np.isnan(np.sum(self.res.y)) and not np.isinf(np.sum(self.res.y)):
                kde = gaussian_kde(self.res.y)
                self.kde.x = np.linspace(np.min(self.res.y)-1, np.max(self.res.y)+1, len(self.res.x))
                self.kde.y = kde.evaluate(self.kde.x)
                self.kde_line.setData(x=-self.kde.x, y=self.kde.y)
                #self.fit_kde()

    def fit_kde(self):
        def gauss(x, *p):
            A, mu, sigma = p
            return A * np.exp(-(x - mu) ** 2 / (2. * sigma ** 2))

        # p0 is the initial guess for the fitting coefficients (A, mu and sigma above)
        p0 = [1., 0., 1.]

        coeff, var_matrix = curve_fit(gauss, self.kde.x, self.kde.y, p0=p0)

        print(coeff)
        # Get the fitted curve
        self.kde_fit.setData(x=-self.kde.x, y=gauss(self.kde.x, *coeff))

    def add_exact_points(self, points, tollerance=1e-6, remove=False, bad=False, redraw=True):
        for p in points:
            self.add_points(p*(1-tollerance), -np.inf, p*(1+tollerance), np.inf, remove=remove, bad=bad, redraw=redraw)

        self.set_fit_mask()
        try:
            self.set_res()
        except:
            pass

    def add_points(self, x1, y1, x2, y2, remove=False, bad=False, redraw=True):
        x1, x2 = min(x1, x2), max(x1, x2)
        y1, y2 = min(y1, y2), max(y1, y2)

        if not bad:
            mask = 'mask'
            points = 'points'
        else:
            mask = 'bad_mask'
            points = 'bad_pixels'

        local_mask = np.logical_and(np.logical_and((self.spec.x() > x1), (self.spec.x() < x2)), np.logical_and((self.spec.y() > y1), (self.spec.y() < y2)))
        if len(local_mask) > 0:
            if not remove:
                getattr(self, mask).set(x=np.logical_or(getattr(self, mask).x(), local_mask))
            else:
                getattr(self, mask).set(x=np.logical_and(getattr(self, mask).x(), np.logical_not(local_mask)))

            if redraw:
                if not bad:
                    self.update_points()
                else:
                    getattr(self, points).setData(x=self.spec.x()[getattr(self, mask).x()], y=self.spec.y()[getattr(self, mask).x()])
        #getattr(self, mask).normalize(not self.parent.normview)

    def update_points(self):
        x, y = np.copy(self.spec.x()), np.copy(self.spec.y())
        if len(x) > 0:
            y[np.logical_not(self.fit_mask.x())] = np.NaN
        if self.parent.selectview == 'point' or 'point' in self.parent.specview:
            self.points.setData(x=x, y=y)
        elif self.parent.selectview == 'color':
            self.points.setData(x=x, y=y, connect='finite')
        elif self.parent.selectview == 'region':
            self.updateRegions()

    def updateRegions(self):
        try:
            for r in self.regions:
                self.parent.vb.removeItem(r)
        except:
            pass

        i = np.where(self.fit_mask.x())
        if i[0].shape[0] > 0:
            ind = np.where(np.diff(np.where(self.fit_mask.x())[0]) > 1)[0]
            ind = np.sort(np.append(np.append(i[0][ind], i[0][ind + 1]), [i[0][-1], i[0][0]]))

            self.regions = []
            for i, k in enumerate(range(0, len(ind), 2)):
                x_r = self.spec.x()[-1] if ind[k+1] > len(self.spec.x())-2 else (self.spec.x()[ind[k+1]+1] + self.spec.x()[ind[k+1]]) / 2
                self.regions.append(VerticalRegionItem([(self.spec.x()[max(0, ind[k]-1)] + self.spec.x()[ind[k]]) / 2, x_r],
                                                       brush=self.region_brush))
                # self.regions.append(pg.LinearRegionItem([self.spec.x()[ind[k]], self.spec.x()[ind[k+1]]], movable=False, brush=pg.mkBrush(100, 100, 100, 30)))
                self.parent.vb.addItem(self.regions[-1])

    def add_spline(self, x, y, name=''):
        getattr(self, 'spline'+name).add(x, y)
        getattr(self, 'spline'+name).sort()
        getattr(self, 'g_spline'+name).setData(x=getattr(self, 'spline'+name).x, y=getattr(self, 'spline'+name).y)
        self.calc_spline(name=name)
        self.update_fit()

    def del_spline(self, x1=None, y1=None, x2=None, y2=None, arg=None, name=''):
        if arg is None:
            x1, x2 = min(x1, x2), max(x1, x2)
            y1, y2 = min(y1, y2), max(y1, y2)
            for i in reversed(range(getattr(self, 'spline'+name).n)):
                if x1 < getattr(self, 'spline'+name).x[i] < x2 and y1 < getattr(self, 'spline'+name).y[i] < y2:
                    getattr(self, 'spline'+name).delete(i)
        else:
            getattr(self, 'spline'+name).delete(arg)
        getattr(self, 'g_spline'+name).setData(x=getattr(self, 'spline'+name).x, y=getattr(self, 'spline'+name).y)
        if getattr(self, 'spline'+name).n > 1:
            self.calc_spline(name=name)
        self.update_fit()

    def calc_spline(self, name=''):
        if getattr(self, 'spline'+name).n > 1:
            k = 3 if getattr(self, 'spline'+name).n > 3 else getattr(self, 'spline'+name).n-1
            tck = splrep(getattr(self, 'spline'+name).x, getattr(self, 'spline'+name).y, k=k)

        if getattr(self, 'spline'+name).n > 1:
            setattr(self, 'cont_mask'+name, (getattr(self, 'spec'+name).raw.x > getattr(self, 'spline'+name).x[0]) & (getattr(self, 'spec'+name).raw.x < getattr(self, 'spline'+name).x[-1]))
            getattr(self, 'cont'+name).set_data(getattr(self, 'spec'+name).raw.x[getattr(self, 'cont_mask'+name)], splev(getattr(self, 'spec'+name).raw.x[getattr(self, 'cont_mask'+name)], tck))
        else:
            setattr(self, 'cont_mask' + name, None)
            setattr(self, 'cont'+name, gline())
        try:
            getattr(self, 'g_cont' + name).setData(x=getattr(self, 'cont'+name).x, y=getattr(self, 'cont'+name).y)
        except:
            pass

    def set_fit_mask(self):
        self.fit_mask.set(x=np.logical_and(self.mask.x(), np.logical_not(self.bad_mask.x())))

    def normalize(self):
        if self.parent.normview and self.cont_mask is not None:
            self.spec.normalize(True)
            self.spec.norm.interpolate()
        else:
            if len(self.fit_comp) > 0:
                for comp in self.fit_comp:
                    comp.normalize(norm=False, cont_mask=False, inter=True)
        self.mask.normalize(self.parent.normview, cont_mask=self.cont_mask is not None)
        self.bad_mask.normalize(self.parent.normview, cont_mask=self.cont_mask is not None)
        self.set_fit_mask()

        if self.fit.norm.n > 0 and not self.parent.normview:
            self.fit.normalize(self.parent.normview, cont_mask=False, inter=True)
            self.fit.raw.interpolate()

        #self.set_fit_mask()
        #self.rewrite_mask()

    def calc_cont(self, xl=None, xr=None, iter=5, window=301):
        if self.spec.raw.n > 0:
            if xl is None:
                xl = self.spec.raw.x[0]
            if xr is None:
                xr = self.spec.raw.x[-1]

            print(xl, xr)
            mask = (xl < self.spec.raw.x) * (self.spec.raw.x < xr)
            ys = self.spec.raw.y[mask]

            for i in range(iter):
                print(np.sum(mask), len(ys), len(self.spec.raw.y[mask]))
                mask[mask] *= (ys - self.spec.raw.y[mask]) / self.spec.raw.err[mask] < 2.5
                ys = sg.savitzky_golay(self.spec.raw.y[mask], window_size=window, order=7)

            inter = interp1d(self.spec.raw.x[mask], ys, fill_value=(ys[0], ys[-1]))

            self.cont_mask = (xl < self.spec.raw.x ) & (self.spec.raw.x < xr)
            self.cont.set_data(self.spec.raw.x[self.cont_mask], inter(self.spec.raw.x[self.cont_mask]))
            self.redraw()

    def findFitLines(self, ind=-1, tlim=0.01, all=True, debug=False):
        """
        Function to prepare lines to fit.
          - ind         : specify component to fit
          - all         : if all then look for all the lines located in the  normalized spectrum

        Prepared lines where fit will be calculated are stored in self.fit_lines list.
        """
        if ind == -1:
            self.fit_lines = MaskableList([])
        elif hasattr(self, 'fit_lines') and len(self.fit_lines) > 0:
            mask = [line.sys != ind for line in self.fit_lines]
            self.fit_lines = self.fit_lines[mask]
        else:
            self.fit_lines = MaskableList([])

        if self.spec.norm.n > 0 and self.cont.n > 0:
            if all:
                x = self.spec.norm.x
            else:
                x = self.spec.norm.x[self.fit_mask.norm.x]
            for sys in self.parent.fit.sys:
                if ind == -1 or sys.ind == ind:
                    for sp in sys.sp.keys():
                        lin = self.parent.atomic.list(sp)
                        for l in lin:
                            l.b = sys.sp[sp].b.val
                            l.logN = sys.sp[sp].N.val
                            l.z = sys.z.val
                            l.recalc = True
                            l.sys = sys.ind
                            l.range = tau(l, resolution=self.resolution).getrange(tlim=tlim)
                            l.cf = -1
                            if self.parent.fit.cf_fit:
                                for i in range(self.parent.fit.cf_num):
                                    cf = getattr(self.parent.fit, 'cf_'+str(i))
                                    cf_sys = cf.addinfo.split('_')[0]
                                    cf_exp = cf.addinfo.split('_')[1] if len(cf.addinfo.split('_')) > 1 else 'all'
                                    if (cf_sys == 'all' or sys.ind == int(cf_sys[3:])) and (cf_exp == 'all' or self.ind() == int(cf_exp[3:])) and l.l()*(1+l.z) > cf.min and l.l()*(1+l.z) < cf.max:
                                        l.cf = i
                            if all:
                                if any([x[0] < p < x[-1] for p in l.range]):
                                    self.fit_lines += [l]
                            else:
                                if np.sum(np.where(np.logical_and(x >= l.range[0], x <= l.range[1]))) > 0:
                                    self.fit_lines += [l]
        if debug:
            print('findFitLines', self.fit_lines, [l.cf for l in self.fit_lines])

    def calcFit(self, ind=-1, recalc=False, redraw=True, timer=False, tau_limit=0.01):
        """

           - ind             : specify the exposure for which fit is calculated
           - recalc          : if True recalculate profile in all lines (given in self.fit_lines)
           - redraw          : if True redraw the fit
        :return:
        """
        if timer:
            t = Timer(str(ind))

        if self.spec.norm.n > 0 and self.cont.n > 0:
            # >>> update line parameters:
            for line in self.fit_lines:
                if ind == -1 or ind == line.sys:
                    if line.recalc or recalc:
                        sys = self.parent.fit.sys[line.sys]
                        line.b = sys.sp[line.name.split()[0]].b.val
                        line.logN = sys.sp[line.name.split()[0]].N.val
                        line.z = sys.z.val
                        line.tau = tau(line, resolution=self.resolution)
            if timer:
                t.time('update')

            # >>> create lambda grid:
            x_spec = self.spec.norm.x
            mask_glob = np.zeros_like(x_spec)
            if 0:
                x = np.asarray([self.spec.norm.x[0], self.spec.norm.x[-1]])
                for line in self.fit_lines:
                    if ind == -1 or ind == line.sys:
                        line.tau.getrange(tlim=tau_limit)
                        mask = np.logical_and(x_spec > line.range[0], x_spec < line.range[1])
                        mask_glob = np.logical_or(mask_glob, mask)
                        #x_grid = line.tau.x_grid(x_spec[mask], num=)
                        x_grid = line.tau.x_grid(ran=line.range)
                        x = np.insert(x, np.searchsorted(x, x_grid), x_grid)
                x = np.insert(x, np.searchsorted(x, x_spec[mask_glob]), x_spec[mask_glob])
            else:
                for line in self.fit_lines:
                    if ind == -1 or ind == line.sys:
                        mask_glob = np.maximum(mask_glob, line.tau.grid_spec(x_spec))
                x = makegrid(x_spec, mask_glob)
                #print(mask_glob[mask_glob != 0])
            if timer:
                t.time('create x')

            # >>> calculate the intrinsic absorption line spectrum
            flux = np.zeros_like(x)
            for line in self.fit_lines:
                if ind == -1 or ind == line.sys:
                    if line.recalc or recalc:
                        line.profile = line.tau.calctau(x, vel=False, verbose=False, convolve=None, tlim=tau_limit)
                        line.recalc = False
                    if not self.parent.fit.cf_fit:
                        flux += line.profile

            # >>> include partial covering:
            if self.parent.fit.cf_fit:
                cfs = []
                for line in self.fit_lines:
                    if ind == -1 or ind == line.sys:
                        cfs.append(line.cf)
                cfs = np.array(cfs)
                for i in np.unique(cfs[cfs > -1]):
                    cf = getattr(self.parent.fit, 'cf_' + str(i)).val
                    profile = np.zeros_like(x)
                    for k in np.where(cfs == i)[0]:
                        profile += self.fit_lines[k].profile
                    flux += - np.log(np.exp(-profile) * (1 - cf) + cf)

            flux = np.exp(-flux)

            if timer:
                t.time('calc profiles')

            # >>> convolve the spectrum with instrument function
            #self.resolution = None
            if self.resolution not in [None, 0]:
                if 0:
                    kernel = (self.spec.x()[-1] + self.spec.x()[0]) / 2 / np.median(np.diff(self.spec.x())) / self.resolution / 2 / np.sqrt(2 * np.log(2))
                    kernel = Gaussian1DKernel(kernel)
                    flux = convolve(flux, kernel, boundary='extend')
                else:
                    #debug(self.resolution, 'res')
                    flux = convolveflux(x, flux, self.resolution, kind='direct')
            if timer:
                t.time('convolve')

            # >>> correct for artificial continuum:
            if self.parent.fit.cont_fit:
                flux = flux * self.correctContinuum(x)

            # >>> set fit graphics
            if ind == -1:
                self.set_fit(x=x, y=flux)
                if redraw:
                    self.set_gfit()
                    self.set_res()
            else:
                self.set_fit_comp(x=x, y=flux, ind=ind)
            if timer:
                t.time('set_fit')


    def calcFit_fft(self, ind=-1, recalc=True, redraw=True, debug=False, tau_limit=0.01):
        """

           - ind             : specify the exposure for which fit is calculated
           - recalc          : if True recalculate profile in all lines (given in self.fit_lines)
           - redraw          : if True redraw the fit
        :return:
        """
        #print(ind, self.spec.norm.n, self.cont.n)
        if self.spec.norm.n > 0 and self.cont.n > 0:
            # >>> update line parameters:
            for line in self.fit_lines:
                if ind == -1 or ind == line.sys:
                    if line.recalc or recalc:
                        sys = self.parent.fit.sys[line.sys]
                        line.b = sys.sp[line.name.split()[0]].b.val
                        line.logN = sys.sp[line.name.split()[0]].N.val
                        line.z = sys.z.val
                        line.tau = tau(line, resolution=self.resolution)

            # >>> create lambda grid:
            for line in self.fit_lines:
                line.tau.getrange(tlim=tau_limit)
            x_min = np.min([line.tau.range[0] for line in self.fit_lines])
            x_max = np.max([line.tau.range[1] for line in self.fit_lines])
            if len(self.spec.x()[self.mask.x()]) > 0:
                x_min = np.min([x_min, np.min(self.spec.x()[self.mask.x()])])
                x_max = np.max([x_max, np.max(self.spec.x()[self.mask.x()])])
            if self.resolution not in [None, 0]:
                x_mid = np.mean([x_min, x_max])
                delta = x_mid / self.resolution / 10
                x_min, x_max = x_min * (1 - 3/self.resolution), x_max * (1 + 3/self.resolution)
            else:
                delta = (self.spec.raw.x[1] - self.spec.raw.x[0])
                # x_min, x_max = x_min - 3 * 2.5 * delta, x_max + 3 * 2.5 * delta
            for l in self.fit_lines:
                delta = min(delta, l.tau.delta())
            num = int((x_max-x_min) / delta)
            #print(x_max, x_min, delta, num)
            x = np.logspace(np.log10(x_min), np.log10(x_max), num)

            mask = np.zeros_like(x, dtype=bool)
            for line in self.fit_lines:
                mask = np.logical_or(mask, np.logical_and(x > line.tau.range[0], x < line.tau.range[1]))
            sigma_n = (x_max + x_min) / 2 / delta / self.resolution / 2 / np.sqrt(2*np.log(2))
            #mask = np.ones(len(x), dtype=bool)
            if np.sum(mask) % 2 == 1:
                mask[np.nonzero(mask == True)[0][0]] = False
            num = np.sum(mask)
            #print(len(x), num)

            # >>> calculate the intrinsic absorption line spectrum
            flux = np.zeros_like(x)
            for line in self.fit_lines:
                if ind == -1 or ind == line.sys:
                    if line.recalc or recalc:
                        line.profile = line.tau.calctau(x, vel=False, verbose=False, convolve=None, tlim=tau_limit)
                        line.recalc = False
                    if not self.parent.fit.cf_fit:
                        flux += line.profile

            # >>> include partial covering:
            if self.parent.fit.cf_fit:
                cfs = []
                for line in self.fit_lines:
                    if ind == -1 or ind == line.sys:
                        cfs.append(line.cf)
                cfs = np.array(cfs)
                for i in np.unique(cfs[cfs > -1]):
                    cf = getattr(self.parent.fit, 'cf_' + str(i)).val
                    profile = np.zeros_like(x)
                    for k in np.where(cfs == i)[0]:
                        profile += self.fit_lines[k].profile
                    flux += - np.log(np.exp(-profile) * (1 - cf) + cf)

            flux = np.exp(-flux)

            # >>> convolve the spectrum with instrument function
            if self.resolution not in [None, 0]:
                f = np.fft.rfft(flux[mask])
                if 0:
                    freq = np.fft.rfftfreq(num, d=(x_max - x_min)/2/np.pi/num)
                    f *= np.exp(- np.power(x_mid/self.resolution/2/np.sqrt(2*np.log(2)) * freq, 2) / 2)
                else:
                    freq = np.fft.rfftfreq(num, d=(num - 0) / 2 / np.pi / num)
                    f *= np.exp(- 0.5 * sigma_n**2 * freq**2)
                flux[mask] = np.fft.irfft(f)

            if debug:
                print('calcFit_fft', x, flux)

            # >>> correct for artificial continuum:
            if self.parent.fit.cont_fit:
                flux = flux * self.correctContinuum(x)


            # >>> set fit graphics
            if ind == -1:
                self.set_fit(x=x, y=flux)
                if redraw:
                    self.update_fit()
            else:
                self.set_fit_comp(x=x, y=flux, ind=ind)

    def calcFit_fast(self, ind=-1, recalc=False, redraw=True, timer=False, num_between=3, tau_limit=0.01):
        """

           - ind             : specify the exposure for which fit is calculated
           - recalc          : if True recalculate profile in all lines (given in self.fit_lines)
           - redraw          : if True redraw the fit
           - num_between     : number of points to add between spectral pixels
           - tau_limit       : limit of optical depth to cutoff the line (set the range of calculations)
        :return:
        """
        if timer:
            t = Timer(str(ind))
        if self.spec.norm.n > 0 and self.cont.n > 0:
            # >>> update line parameters:
            for line in self.fit_lines:
                if ind == -1 or ind == line.sys:
                    if line.recalc or recalc:
                        sys = self.parent.fit.sys[line.sys]
                        line.b = sys.sp[line.name.split()[0]].b.val
                        line.logN = sys.sp[line.name.split()[0]].N.val
                        line.z = sys.z.val
                        line.tau = tau(line, resolution=self.resolution)
            if timer:
                t.time('update')

            # >>> create lambda grid:
            if self.resolution not in [None, 0]:
                if ind == -1:
                    x_spec = self.spec.norm.x
                    #mask_glob = np.zeros_like(x_spec)
                    mask_glob = self.mask.norm.x
                    for line in self.fit_lines:
                        if ind == -1 or ind == line.sys:
                            line.tau.getrange(tlim=tau_limit)
                            mask_glob = np.logical_or(mask_glob, ((x_spec > line.tau.range[0]) * (x_spec < line.tau.range[-1])))
                    x = makegrid(x_spec, mask_glob.astype(int) * num_between)
                else:
                    x = self.fit.norm.x
            else:
                x = self.spec.norm.x
            if timer:
                t.time('create x')

            # >>> calculate the intrinsic absorption line spectrum
            flux = np.zeros_like(x)
            for line in self.fit_lines:
                if ind == -1 or ind == line.sys:
                    if line.recalc or recalc:
                        line.profile = line.tau.calctau(x, vel=False, verbose=False, convolve=None, tlim=tau_limit)
                        line.recalc = False
                    if not self.parent.fit.cf_fit:
                        flux += line.profile

            # >>> include partial covering:
            if self.parent.fit.cf_fit:
                cfs, inds = [], []
                for i, line in enumerate(self.fit_lines):
                    if ind == -1 or ind == line.sys:
                        cfs.append(line.cf)
                        inds.append(i)
                cfs = np.array(cfs)
                for i in np.unique(cfs):
                    if i > -1:
                        cf = getattr(self.parent.fit, 'cf_' + str(i)).val
                    else:
                        cf = 0
                    profile = np.zeros_like(x)
                    for k in np.where(cfs == i)[0]:
                        profile += self.fit_lines[inds[k]].profile
                    flux += - np.log(np.exp(-profile) * (1 - cf) + cf)

            flux = np.exp(-flux)

            if timer:
                t.time('calc profiles')

            # >>> convolve the spectrum with instrument function
            #self.resolution = None
            if self.resolution not in [None, 0]:
                if 0:
                    kernel = (self.spec.x()[-1] + self.spec.x()[0]) / 2 / np.median(np.diff(self.spec.x())) / self.resolution / 2 / np.sqrt(2 * np.log(2))
                    kernel = Gaussian1DKernel(kernel)
                    flux = convolve(flux, kernel, boundary='extend')
                else:
                    #debug(self.resolution, 'res')
                    flux = convolveflux(x, flux, self.resolution, kind='direct')
            if timer:
                t.time('convolve')

            # >>> correct for artificial continuum:
            if self.parent.fit.cont_fit:
                flux = flux * self.correctContinuum(x)

            # >>> correct for artificial continuum:
            if self.parent.fit.disp_fit:
                for i in range(self.parent.fit.disp_num):
                    if getattr(self.parent.fit, 'dispz_' + str(i)).addinfo == 'exp_' + str(self.ind()):
                        f = interp1d(x + (x - getattr(self.parent.fit, 'dispz_' + str(i)).val) * getattr(self.parent.fit, 'disps_' + str(i)).val, flux, bounds_error=False, fill_value=1)
                        flux = f(x)

            # >>> set fit graphics
            if ind == -1:
                self.set_fit(x=x, y=flux)
                if redraw:
                    print('redraw')
                    self.set_gfit()
                    self.set_res()
            else:
                self.set_fit_comp(x=x, y=flux, ind=ind)

            if timer:
                t.time('set_fit')

    def correctContinuum(self, x):
        """
        Calculate the correction to the continuum given chebyshev polinomial coefficients in self.fit
        """
        print('correctCont:', self.parent.fit.cont_num, self.parent.fit.cont_left, self.parent.fit.cont_right)
        if len(x) > 0:
            cheb = np.array([getattr(self.parent.fit, 'cont'+str(i)).val for i in range(self.parent.fit.cont_num)])
            base = (x - x[0]) * 2 / (x[-1] - x[0]) - 1
            if 1:
                return np.polynomial.chebyshev.chebval(base, cheb)
            else:
                base = np.cos(np.outer(base, np.arange(self.parent.fit.cont_num)))
                return np.sum(np.multiply(base, cheb), axis=1)

    def chi(self):
        mask = self.fit_mask.x()
        spec = self.spec
        if len(spec.x()) > 0 and np.sum(mask) > 0 and self.fit.n() > 0:
            return ((self.spec.y()[mask] - self.fit.f(self.spec.x()[mask])) / self.spec.err()[mask])
        else:
            return np.asarray([])

    def chi2(self):
        mask = self.fit_mask.norm.x
        spec = self.spec.norm
        chi2 = np.sum(np.power(((spec.y[mask] - self.fit.norm.f(spec.x[mask])) / spec.err[mask]), 2))
        return chi2

    def selectCosmics(self):
        y_sm = scipy.signal.medfilt(self.spec.y, 5)
        sigma = scipy.signal.medfilt(self.spec.err, 101)
        bad = np.abs(self.spec.y - y_sm) / sigma > 4.0
        self.bad_mask = np.logical_or(self.bad_mask, bad)
        self.remove()
        self.init_GU()

    def smooth(self, kind='astropy'):
        print('smoothing: ', self.filename)
        mask = np.logical_and(self.spec.y() != 0, self.spec.err() != 0)
        m = np.logical_and(np.logical_not(self.bad_mask.x()), mask)

        if kind == 'astropy':
            stddev = 1000.0 / 299794.25 * np.median(self.spec.x()) / np.median(np.diff(self.spec.x()))
            print(stddev)
            y = convolve(self.spec.y()[m], Gaussian1DKernel(stddev=stddev), boundary='extend')

        elif kind == 'convolveflux':
            y = convolveflux(self.spec.x()[m], self.spec.y()[m], 200.0, kind='gauss')

        elif kind == 'regular':
            d = 5
            y, lmbd = ds.smooth_data(self.spec.x()[m], self.spec.y()[m], d, xhat=np.linspace(self.spec.x()[m][0], self.spec.x()[m][-1], 1000))

        inter = interp1d(self.spec.x()[m], y, bounds_error=False,
                         fill_value=(y[0], y[-1]), assume_sorted=True)
        self.sm.set(x=self.spec.x()[mask], y=inter(self.spec.x()[mask]))
        self.sm.raw.interpolate(fill_value=(self.sm.raw.y[0], self.sm.raw.y[-1]))
        self.cont.x, self.cont.y = self.sm.x(), self.sm.y()
        self.redraw()
        #self.g_cont.setData(x=self.cont.x, y=self.cont.y)

    def rebinning(self, factor):
        print(factor)
        if factor == 0:
            self.parent.vb.removeItem(self.rebin)
            self.rebin = None
        else:
            if self.rebin is None:
                #self.rebin = plotStepSpectrum(x=[], y=[], stepMode=True)
                self.rebin = pg.PlotCurveItem(x=[], y=[], pen=pg.mkPen(250, 100, 0, width=4))
                self.parent.vb.addItem(self.rebin)

            n = self.spec.raw.x.shape[0] // factor
            x = self.spec.raw.x[:n * factor].reshape(self.spec.raw.x.shape[0] // factor, factor).sum(1) / factor
            y = self.spec.raw.y[:n * factor].reshape(self.spec.raw.x.shape[0] // factor, factor).sum(1) / factor
            #y, err = spectres(self.spec.raw.x, self.spec.raw.y, x1, spec_errs=self.spec.raw.err)
            self.rebin.setData(x=x, y=y)

    def auto_select(self, x):
        ind = self.spec.index(x)
        i = ind
        while (not self.parent.normview and self.cont.f(self.spec.x()[i]) - self.spec.y()[i] > self.spec.err()[i]) or (self.parent.normview and 1 - self.spec.y()[i] > self.spec.err()[i]):
            self.add_exact_points([self.spec.x()[i]])
            i += 1
        self.add_exact_points([self.spec.x()[i]])
        i = ind
        while (not self.parent.normview and self.cont.f(self.spec.x()[i]) - self.spec.y()[i] > self.spec.err()[i]) or (self.parent.normview and 1 - self.spec.y()[i] > self.spec.err()[i]):
            self.add_exact_points([self.spec.x()[i]])
            i -= 1
        self.add_exact_points([self.spec.x()[i]])

    def apply_regions(self):
        regions = []
        for r in self.parent.plot.regions:
            if not r.active:
                    regions.append(r.size_full)
        self.spec.apply_region(regions)
        self.redraw()

    def apply_shift(self, vel):
        """
        apply shift of wavelenght in velocity space, specified by vel
        """
        factor = (1 + vel/ac.c.to('km/s').value)
        self.spec.raw.x *= factor
        if len(self.cont.x) > 0:
            print('shift cont')
            self.cont.x *= factor
        if len(self.fit.raw.x) > 0:
            print('shift fit')
            self.fit.raw.x *= factor
        print('Converted to Heliocentric velocities, helio_vel:', vel)

    def airvac(self):
        """
        correct from air to vacuum wavelenghts
        """
        n = 1.0
        for i in range(5):
            n_it = n
            sig2 = 1.0e8 / (self.spec.raw.x * self.spec.raw.x * n_it * n_it)
            n = 1.0e-8 * (15997.0 / (38.90 - sig2) + 2406030.0 / (130.0 - sig2) + 8342.13) + 1.0
        self.spec.raw.x *= n
        print('Converted to air-vacuum wavelenghts')

    def specClicked(self):
        if self.parent.plot.e_status:
            for i, s in enumerate(self.parent.s):
                if self == s:
                    self.parent.s.setSpec(i)
                    return

            #self.g_line.setPen(pg.mkPen(255, 255, 255))


    def mouseDragEvent(self, ev):
        
        if self.parent.plot.e_status:
            if ev.button() != Qt.LeftButton:
                ev.ignore()
                return
            
            if ev.isStart():
                # We are already one step into the drag.
                # Find the point(s) at the mouse cursor when the button was first 
                # pressed:
                pos = self.parent.parent.vb.mapSceneToView(ev.pos())
                self.st_pos = pos.x()
            
            pos = self.parent.parent.vb.mapSceneToView(ev.pos())
            self.parent.parent.delta += (pos.x() - self.st_pos)/self.line.l()
            self.parent.s[self.parent.s.s_ind].spec_x -= self.st_pos - pos.x()
            self.st_pos = pos.x()
            self.parent.s[self.parent.s.s_ind].redraw()
            ev.accept() 

class regionList(list):
    def __init__(self, parent):
        super(regionList).__init__()
        self.parent = parent

    def check(self, reg):
        if isinstance(reg, str):
            if reg in [str(r) for r in self]:
                return [str(r) for r in self].index(reg)
        elif isinstance(reg, regionItem):
            if reg in self:
                return self.index(reg)

    def add(self, reg=None):
        if reg is None or (self.check(reg) is None and len(re.findall('[\d\.]+\.\.[\d\.]+', reg))>0):
            if reg is None:
                self.append(regionItem(self))
            else:
                self.append(regionItem(self, xmin=float(reg.split()[0].split('..')[0]), xmax=float(reg.split()[0].split('..')[1])))
                if len(reg.split()) > 1:
                    self[-1].addinfo = ' '.join(reg.split()[1:])

            self.parent.vb.addItem(self[-1])

    def remove(self, reg):
        i = self.check(reg)
        if i is not None:
            self.parent.vb.removeItem(self[i])
            del self[i]

    def fromText(self, text):
        for i in reversed(range(len(self))):
            self.remove(str(self[i]))
        for reg in text.splitlines():
            self.add(reg)

    def __str__(self):
        return '\n'.join([str(r) for r in self])

class regionItem(pg.LinearRegionItem):
    def __init__(self, parent, brush=pg.mkBrush(173, 173, 173, 100), xmin=None, xmax=None, addinfo=''):
        self.parent = parent
        if xmin is None:
            xmin = self.parent.parent.mousePoint_saved.x()
        if xmax is None:
            xmax = self.parent.parent.mousePoint_saved.x()
        super().__init__(values=[xmin, xmax],
                         orientation=pg.LinearRegionItem.Vertical,
                         brush=brush)
        self.active = True
        self.activeBrush = brush
        self.activeBrush.setStyle(Qt.SolidPattern)
        self.activePen = pg.mkPen(brush.color())
        self.updateLines()

        self.inactivePen = pg.mkPen(150, 150, 150, 255, style=Qt.DashLine)
        self.inactiveBrush = pg.mkBrush(100, 100, 100, 255)
        self.inactiveBrush.setStyle(Qt.Dense5Pattern)

        self.addinfo = addinfo

    def updateLines(self):
        if self.active:
            for l in self.lines:
                l.setPen(self.activePen)
                c = self.brush.color()
                c.setAlpha(255)
                l.setHoverPen(pg.mkPen(c))
                #l.setHoverPen(QPen(c))
        else:
            for l in self.lines:
                l.setPen(self.inactivePen)
                l.setHoverPen(self.inactivePen)

    def hoverEvent(self, ev):
        self.lines[0].setMovable((QApplication.keyboardModifiers() == Qt.ShiftModifier))
        self.lines[1].setMovable((QApplication.keyboardModifiers() == Qt.ShiftModifier))
        #if (QApplication.keyboardModifiers() == Qt.ShiftModifier):
        #    super(regionItem).hoverEvent(ev)

    def setMouseHover(self, hover):
        ## Inform the item that the mouse is(not) hovering over it
        if self.mouseHovering == hover:
            return
        self.mouseHovering = hover
        if hover:
            c = self.brush.color()
            #c.setAlpha(c.alpha() / 2)
            self.currentBrush = pg.mkBrush(c)
        else:
            self.currentBrush = self.brush
        self.update()

    def mouseDragEvent(self, ev):
        if (QApplication.keyboardModifiers() == Qt.ShiftModifier):
            super().mouseDragEvent(ev)

    def mouseClickEvent(self, ev):

        if ev.double():
            self.active = not self.active
            self.setMovable(self.active) # and (QApplication.keyboardModifiers() == Qt.ShiftModifier))
            if self.active:
                self.setBrush(self.activeBrush)
                self.setRegion(self.size_full)
            else:
                self.size_full = self.getRegion()
                self.setRegion([self.size_full[0], self.size_full[0]+1])
                self.setBrush(self.inactiveBrush)
            self.updateLines()
            self.parent.parent.updateRegions()

        if ev.button() == Qt.LeftButton:
            if (QApplication.keyboardModifiers() == Qt.ControlModifier):
                self.parent.remove(self)

    #def __eq__(self, other):
    #    return (self.xmin == other.xmin) * (self.xmax == other.xmax)

    def __str__(self):
        return "{0:.1f}..{1:.1f} ".format(self.getRegion()[0], self.getRegion()[1]) + self.addinfo

class SpectrumFilter():
    def __init__(self, parent, name=None):
        self.parent = parent
        self.name = name
        if name is 'u':
            self.color = (23, 190, 207)
            self.m0 = 22.12
            self.b = 1.4e-10
        if name is 'g':
            self.color = (44, 160, 44)
            self.m0 = 22.60
            self.b = 0.9e-10
        if name is 'r':
            self.color = (214, 39, 40)
            self.m0 = 22.29
            self.b = 1.2e-10
        if name is 'i':
            self.color = (227, 119, 194)
            self.m0 = 21.85
            self.b = 1.8e-10
        if name is 'z':
            self.color = (31, 119, 180)
            self.m0 = 20.32
            self.b = 7.4e-10
        self.data = None
        self.gobject = None
        self.read_data()
        self.get_value()

    def read_data(self):
        data = np.genfromtxt(os.path.dirname(os.path.realpath(__file__)) + r'/data/SDSS/' + self.name + '.dat',
                             skip_header=6, usecols=(0, 1), unpack=True)
        self.data = gline(x=data[0], y=data[1])
        self.flux_0 = np.trapz(3.631 * 3e-18 / self.data.x * self.data.y, x=self.data.x)
        print(self.name, self.flux_0)
        self.ymax_pos = np.argmax(self.data.y)
        self.inter = interp1d(self.data.x, self.data.y, bounds_error=False, fill_value=0, assume_sorted=True)

    def update(self, level):
        self.gobject.setData(x=self.data.x, y=level * self.data.y)
        self.get_value()
        self.label.setText(self.name + ':' + "{:0.2f}".format(self.value))
        self.label.setPos(self.data.x[self.ymax_pos], level * self.data.y[self.ymax_pos])

    def set_gobject(self, level):
        self.gobject = pg.PlotCurveItem(x=self.data.x, y=level * self.data.y, pen=pg.mkPen(color=self.color, width=0.5),
                                        fillLevel=0, brush=pg.mkBrush(self.color + (3,)))
        self.label = pg.TextItem(text=self.name + ':' + "{:0.2f}".format(self.value), anchor=(0, 1.2), color=self.color)
        self.label.setFont(QFont("SansSerif", 16))
        self.label.setPos(self.data.x[self.ymax_pos], level * self.data.y[self.ymax_pos])

    def get_value(self, x=None, y=None):
        try:
            m0 = -2.5 / np.log(10) * (np.log(self.b))
            if x is None or y is None:
                x, y = self.parent.s[self.parent.s.ind].spec.x(), self.parent.s[self.parent.s.ind].spec.y()
            mask = np.logical_and(x > self.data.x[0], x < self.data.x[-1])
            x, y = x[mask], y[mask]
            flux = np.trapz(y * 1e-33 * x * self.inter(x), x=x)
            self.value = -2.5 / np.log(10) * (np.arcsinh(flux / self.flux_0 / 2 / self.b) + np.log(self.b))
        except:
            self.value = np.nan
        return self.value


class VerticalRegionItem(pg.UIGraphicsItem):

    def __init__(self, range=[0, 1],  brush=None):
        """Create a new LinearRegionItem.

        ==============  =====================================================================
        **Arguments:**
        range           A list of the positions of the lines in the region. These are not
                        limits; limits can be set by specifying bounds.
        brush           Defines the brush that fills the region. Can be any arguments that
                        are valid for :func:`mkBrush <pyqtgraph.mkBrush>`. Default is
                        transparent blue.
        ==============  =====================================================================
        """

        pg.UIGraphicsItem.__init__(self)
        self.bounds = QRectF()
        self.range = range

        if brush is None:
            brush = pg.mkBrush()
        self.setBrush(brush)


    def setBrush(self, *br, **kargs):
        """Set the brush that fills the region. Can have any arguments that are valid
        for :func:`mkBrush <pyqtgraph.mkBrush>`.
        """
        self.brush = pg.mkBrush(*br, **kargs)
        self.currentBrush = self.brush

    def boundingRect(self):
        br = pg.UIGraphicsItem.boundingRect(self)
        br.setLeft(self.range[0])
        br.setRight(self.range[1])
        return br.normalized()

    def paint(self, p, *args):
        pg.UIGraphicsItem.paint(self, p, *args)
        p.setBrush(self.currentBrush)
        p.setPen(pg.mkPen(None))
        p.drawRect(self.boundingRect())


