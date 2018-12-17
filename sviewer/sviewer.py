from adjustText import adjust_text
from astropy.io import fits
from astropy.table import Table
from collections import OrderedDict
from copy import deepcopy
import emcee
import h5py
import inspect
from lmfit import Minimizer, Parameters, report_fit, fit_report, conf_interval, printfuncs
import matplotlib.pyplot as plt
from matplotlib.ticker import AutoMinorLocator, MultipleLocator, FormatStrFormatter
from multiprocessing import Process
import pickle
import os
import platform
from PyQt5.QtWidgets import (QApplication, QMessageBox, QMainWindow, QWidget, QDesktopWidget,
                             QAction, QActionGroup, qApp, QFileDialog, QTextEdit, QVBoxLayout,
                             QSplitter, QFrame, QLineEdit, QLabel, QPushButton, QCheckBox,
                             QGridLayout, QTabWidget, QFormLayout, QHBoxLayout, QRadioButton,
                             QTreeWidget, QComboBox, QTreeWidgetItem, QAbstractItemView,
                             QStatusBar, QMenu, QButtonGroup, QMessageBox)
from PyQt5.QtCore import Qt, QPoint, QRectF, QEvent, QUrl
from PyQt5.QtGui import QDesktopServices
import tarfile

from ..XQ100 import load_QSO
from ..plot_spec import *
from ..profiles import add_LyaForest, add_ext, add_ext_bump, add_LyaCutoff, convolveflux, tau
from ..a_unc import a
from ..stats import distr1d, distr2d
from .console import *
from .external import spectres
from .fit_model import *
from .fit import *
from .graphics import *
from .lines import *
from .sdss_fit import *
from .tables import *
from .obs_tool import *
from .colorcolor import *
from .utils import *

def lnprob(x, pars, prior, self):
    return lnprior(x, pars, prior) + lnlike(x, pars, self)

def lnprior(x, pars, prior):
    lp = 0
    for k, v in prior.items():
        if k in pars:
            lp += v.lnL(x[pars.index(k)])
    return lp

def lnlike(x, pars, self):
    res = True
    for xi, p in zip(x, pars):
        res *= self.parent.fit.setValue(p, xi)
    self.parent.fit.update()
    self.parent.s.calcFit(recalc=True, redraw=False, timer=False)
    chi = self.parent.s.chi2()
    if res and not np.isnan(chi):
        return -chi
    else:
        return -np.inf

class plotSpectrum(pg.PlotWidget):
    """
    class for plotting main spectrum widget
    class for plotting main spectrum widget
    based on pg.PlotWidget
    """
    def __init__(self, parent):
        bottomaxis = pg.AxisItem(orientation='bottom')
        #stringaxis.setTickSpacing(minor=[(10, 0)])
        bottomaxis.setStyle(tickLength=-15, tickTextOffset=2)
        topaxis = pg.AxisItem(orientation='top')
        #topaxis.setStyle(tickLength=-15, tickTextOffset=2, stopAxisAtTick=(True, True))
        pg.PlotWidget.__init__(self, axisItems={'bottom': bottomaxis, 'top': topaxis}, background=(29,29,29))
        #self.vb = pg.PlotWidget.getPlotItem(self).getViewBox()
        self.parent = parent
        self.initstatus()
        self.vb = self.getViewBox()
        self.customMenu = True
        self.vb.setMenuEnabled(not self.customMenu)
        self.vb.disableAutoRange()
        self.regions = regionList(self)
        self.cursorpos = pg.TextItem(anchor=(0, 1))
        self.vb.addItem(self.cursorpos, ignoreBounds=True)
        self.specname = pg.TextItem(anchor=(1, 1))
        self.vb.addItem(self.specname, ignoreBounds=True)
        self.w_region = None
        self.menu = None  # Override pyqtgraph ViewBoxMenu
        self.menu = self.getMenu()  # Create the menu

        self.v_axis = pg.ViewBox(enableMenu=False)
        self.v_axis.setYLink(self)  #this will synchronize zooming along the y axis
        self.showAxis('top')
        self.scene().addItem(self.v_axis)
        self.v_axis.setGeometry(self.getPlotItem().sceneBoundingRect())
        self.getAxis('top').setStyle(tickLength=-15, tickTextOffset=2, stopAxisAtTick=(False, False))
        self.getAxis('top').linkToView(self.v_axis)
        self.getPlotItem().sigRangeChanged.connect(self.updateVelocityAxis)

    def initstatus(self):
        self.a_status = False
        self.b_status = False
        self.c_status = False
        self.d_status = False
        self.e_status = False
        self.h_status = False
        self.i_status = False
        self.m_status = False
        self.p_status = False
        self.r_status = False   
        self.s_status = False
        self.u_status = False
        self.w_status = False
        self.x_status = False
        self.z_status = False
        self.mouse_moved = False
        self.saveState = None
        self.addline = None
        self.doublet = [None, None]
        self.doublets = doubletList(self)
        self.pcRegions = []
        self.instr_file = None
        self.instr_widget = None
        self.instr_plot = None
        self.showfullfit = False
        self.restframe = True
    
    def set_range(self, x1, x2):
        self.vb.disableAutoRange()
        s = self.parent.s[self.parent.s.ind].spec
        mask = np.logical_and(s.x() > x1, s.x() < x2)
        self.vb.setRange(xRange=(x1, x2), yRange=(np.min(s.y()[mask]), np.max(s.y()[mask])))
    
    def updateVelocityAxis(self):
        self.v_axis.setGeometry(self.getPlotItem().sceneBoundingRect())
        self.v_axis.linkedViewChanged(self.getViewBox(), self.v_axis.YAxis)
        MainPlotXMin, MainPlotXMax = self.viewRange()[0]
        if self.restframe:
            AuxPlotXMin, AuxPlotXMax = MainPlotXMin / (self.parent.z_abs + 1), MainPlotXMax / (self.parent.z_abs + 1)
        else:
            AuxPlotXMin = (MainPlotXMin/(self.parent.z_abs + 1)/self.parent.line_reper.l() - 1)*ac.c.to('km/s').value
            AuxPlotXMax = (MainPlotXMax/(self.parent.z_abs + 1)/self.parent.line_reper.l() - 1)*ac.c.to('km/s').value
        self.v_axis.setXRange(AuxPlotXMin, AuxPlotXMax, padding=0)

    def raiseContextMenu(self, ev):
        """
        Raise the context menu
        """
        menu = self.getMenu()
        menu.popup(ev.screenPos().toPoint())

    def getMenu(self):
        """
        Create the menu
        """
        if self.menu is None:
            self.menu = QMenu()
            self.menu.setStyleSheet(open('config/styles.ini').read())
            self.viewAll = QAction("View all", self.menu)
            self.viewAll.triggered.connect(self.autoRange)
            self.menu.addAction(self.viewAll)
            self.export = QAction("Export...", self.menu)
            self.export.triggered.connect(self.showExportDialog)
            self.exportDialog = None
            self.menu.addSeparator()
            self.menu.addAction(self.export)

        return self.menu

    def showExportDialog(self):
        if self.exportDialog is None:
            self.exportDialog = exportDialog.ExportDialog(self)
        self.exportDialog.show() #self.contextMenuItem)

    def keyPressEvent(self, event):
        super(plotSpectrum, self).keyPressEvent(event)
        key = event.key()

        if not event.isAutoRepeat():

            if event.key() == Qt.Key_Down or event.key() == Qt.Key_Right:
                if self.e_status:
                    self.parent.s.setSpec(self.parent.s.ind + 1)

                if self.p_status:
                    self.parent.fitPoly(np.max([0, self.parent.polyDeg-1]))

            if event.key() == Qt.Key_Up or event.key() == Qt.Key_Left:
                if self.e_status:
                    self.parent.s.setSpec(self.parent.s.ind - 1)

                if self.p_status:
                    self.parent.fitPoly(self.parent.polyDeg + 1)

            if event.key() == Qt.Key_A:
                if (QApplication.keyboardModifiers() == Qt.ControlModifier):
                    self.parent.fit.delSys(self.parent.comp)
                    try:
                        self.parent.fitModel.tab.removeTab(self.parent.comp)
                        for i in range(self.parent.fitModel.tabNum):
                            self.parent.fitModel.tab.setTabText(i, "sys {:}".format(i + 1))
                            self.parent.fitModel.tab.widget(i).ind = i
                    except:
                        pass
                    self.parent.comp -= 1
                    self.parent.s.refreshFitComps()
                    self.parent.showFit(all=self.showfullfit)
                    try:
                        self.parent.fitModel.onTabChanged()
                    except:
                        pass
                else:
                    self.vb.setMouseMode(self.vb.RectMode)
                    self.vb.rbScaleBox.hide()
                    self.a_status = True

            if event.key() == Qt.Key_B:
                if not self.parent.normview:
                    self.vb.setMouseMode(self.vb.RectMode)
                    self.b_status = True
                    self.mouse_moved = False
                    self.parent.statusBar.setText('B-spline mode' )
            
            if event.key() == Qt.Key_C:

                if (QApplication.keyboardModifiers() == Qt.ShiftModifier):
                    l = ['all', 'one', 'none']
                    ind = l.index(self.parent.comp_view)
                    ind += 1
                    if ind > 2:
                        ind = 0
                    print(ind, self.parent.comp_view)
                    self.parent.comp_view = l[ind]
                    d = {0: "Don't show components", 1: "Show only selected component", 2: "Show all components"}
                    self.parent.statusBar.setText(d[ind])
                    self.parent.s.redraw()
                else:
                    self.c_status = 1
                    self.vb.setMouseMode(self.vb.RectMode)
                    self.vb.rbScaleBox.hide()

            if event.key() == Qt.Key_D:
                self.vb.setMouseMode(self.vb.RectMode)
                self.d_status = True
                self.parent.statusBar.setText('Points selection mode')

            if event.key() == Qt.Key_E:
                if (QApplication.keyboardModifiers() == Qt.ControlModifier):
                    self.parent.s.remove(self.parent.s.ind)
                else:
                    self.e_status = True

            if event.key() == Qt.Key_F:
                if (QApplication.keyboardModifiers() != Qt.ControlModifier):
                    if QApplication.keyboardModifiers() == Qt.ShiftModifier:
                        self.showfullfit = True
                    else:
                        self.showfullfit = False
                    self.parent.showFit(all=self.showfullfit)

            if event.key() == Qt.Key_H:
                self.h_status = True
                self.parent.statusBar.setText('Lya select')

            if event.key() == Qt.Key_I:
                if (QApplication.keyboardModifiers() == Qt.ShiftModifier):
                    if self.instr_file is None:
                        self.instr_file = open('temp/instr_func.dat', 'w')
                    if self.instr_widget is None:
                        self.instr_widget = MatplotlibWidget()
                        self.instr_plot = self.instr_widget.getFigure().add_subplot(111)
                        self.instr_widget.show()
                    l, res, err = (self.parent.fit.getValue('z_0')+1)*1215.6701, int(self.parent.fit.getValue('res')), int(self.parent.fit.getValue('res', attr='unc'))
                    s = '{0:6.1f} {1:5d} {2:5d} \n'.format(l, res, err)
                    self.instr_file.write(s)
                    self.instr_file.flush()
                    self.instr_plot.errorbar([l], [res], yerr=[err])
                    self.instr_widget.draw()
                    self.parent.statusBar.setText('data added to temp/instr_func.dat')
                else:
                    self.i_status = True
                    self.parent.statusBar.setText('Estimate the width of Instrument function')

            if event.key() == Qt.Key_M:
                self.m_status = True
                self.parent.statusBar.setText('Rebin mode')

            if event.key() == Qt.Key_N:
                self.parent.normalize(not self.parent.panel.normalize.isChecked())

            if event.key() == Qt.Key_P:
                self.p_status = True
                self.parent.statusBar.setText('Add partial coverage region')

            if event.key() == Qt.Key_R:
                if (QApplication.keyboardModifiers() == Qt.ControlModifier):
                    pass
                    #self.parent.showResiduals.toggle()
                    #self.parent.showResidualsPanel()
                elif (QApplication.keyboardModifiers() == Qt.ShiftModifier):
                    self.restframe = 1 - self.restframe
                    self.updateVelocityAxis()
                else:
                    self.vb.setMouseMode(self.vb.RectMode)
                    self.r_status = True
                    self.parent.statusBar.setText('Set region mode')
                    #self.vb.removeItem(self.w_label)
               
            if event.key() == Qt.Key_S:
                self.vb.setMouseMode(self.vb.RectMode)
                self.s_status = True
                self.parent.statusBar.setText('Points selection mode')

            if event.key() == Qt.Key_T:
                if (QApplication.keyboardModifiers() == Qt.ControlModifier):
                    if self.parent.fitResults is None:
                        self.parent.showFitResults()
                    else:
                        self.parent.fitResults.close()

            if event.key() == Qt.Key_Q:
                self.parent.calc_cont()

            if event.key() == Qt.Key_U:
                self.u_status += 1
                self.parent.statusBar.setText('Find doublet mode')

            if event.key() == Qt.Key_V:
                self.parent.s[self.parent.s.ind].remove()
                sl = ['step', 'steperr', 'line', 'lineerr', 'point', 'pointerr']
                self.parent.specview = sl[(sl.index(self.parent.specview)+1)*int((sl.index(self.parent.specview)+1) < len(sl))]
                self.parent.options('specview', self.parent.specview)
                self.parent.s[self.parent.s.ind].init_GU()
                
            if event.key() == Qt.Key_W:
                if self.w_region is not None and not event.isAutoRepeat():
                    self.vb.removeItem(self.w_region)
                    self.vb.removeItem(self.w_label)
                    self.w_region = None
                else:
                    self.vb.setMouseMode(self.vb.RectMode)
                    self.w_status = True

            if event.key() == Qt.Key_X:
                self.vb.setMouseMode(self.vb.RectMode)
                self.x_status = True
                self.parent.statusBar.setText('Select bad pixels mode')

            if event.key() == Qt.Key_Z:
                if (QApplication.keyboardModifiers() != Qt.ControlModifier):
                    self.vb.setMouseMode(self.vb.RectMode)
                    self.z_status = True
                    self.parent.statusBar.setText('Zooming mode')
                    if not event.isAutoRepeat():
                        self.saveState = self.vb.getState()
                else:
                    if self.saveState is not None:
                        if 1:
                            a = np.array(self.saveState['targetRange']).flatten()
                            self.vb.setRange(QRectF(a[0], a[2], a[1]-a[0], a[3]-a[2]))
                        else:
                            self.vb.setState(self.saveState)
                #vb = self.plot.getPlotItem(self).getViewBox()
                #vb.setMouseMode(ViewBox.RectMode)
        else:
            if event.key() == Qt.Key_C:
                if self.c_status == 2:
                    self.vb.setMouseMode(self.vb.RectMode)
                    self.vb.rbScaleBox.hide()

    def keyReleaseEvent(self, event):

        if not event.isAutoRepeat():

            if event.key() == Qt.Key_A:
                self.a_status = False

            if event.key() == Qt.Key_B:
                self.b_status = False
                if not self.mouse_moved:
                    self.parent.s[self.parent.s.ind].add_spline(self.mousePoint.x(), self.mousePoint.y())

            if event.key() == Qt.Key_C:
                if (QApplication.keyboardModifiers() != Qt.ShiftModifier):
                    if self.c_status == 1:
                        self.parent.comp += 1
                        if self.parent.comp > len(self.parent.fit.sys) - 1:
                            self.parent.comp = 0
                        self.parent.statusBar.setText("Show {:d} component".format(self.parent.comp))
                        try:
                            self.parent.fitModel.tab.setCurrentIndex(self.parent.comp)
                        except:
                            pass
                        #self.parent.s.redraw()
                        self.parent.s.redrawFitComps()
                        self.parent.abs.redraw(z=self.parent.fit.sys[self.parent.comp].z.val)
                    self.c_status = False

            if event.key() == Qt.Key_D:
                self.d_status = False

            if event.key() == Qt.Key_E:
                self.e_status = False

            if event.key() == Qt.Key_H:
                self.h_status = False

            if event.key() == Qt.Key_I:
                self.i_status = False

            if event.key() == Qt.Key_M:
                self.m_status = False

            if event.key() == Qt.Key_O:
                self.parent.UVESSetup_status += 1
                if self.parent.UVESSetup_status > len(self.parent.UVESSetups):
                    self.parent.UVESSetup_status = 0
                self.parent.chooseUVESSetup()

            if event.key() == Qt.Key_R:
                self.r_status = False

            if event.key() == Qt.Key_S:
                self.s_status = False

            if event.key() == Qt.Key_P:
                self.p_status = False

            if event.key() == Qt.Key_U:
                if self.u_status:
                    if len(self.doublets) == 0 or self.doublets[-1].temp is None:
                        self.doublets.append(Doublet(self))
                        self.doublets[-1].draw_temp(self.mousePoint.x())
                    else:
                        self.doublets[-1].find(self.doublets[-1].line_temp.value(), self.mousePoint.x())
                        self.doublets.update()
                self.u_status = False

            if event.key() == Qt.Key_W:
                self.w_status = False

            if event.key() == Qt.Key_X:
                self.x_status = False

            if event.key() == Qt.Key_Z:
                self.z_status = False
        
            if any([event.key() == getattr(Qt, 'Key_'+s) for s in 'ABCDRSXZ']):
                self.vb.setMouseMode(self.vb.PanMode)
                self.parent.statusBar.setText('')

        if event.isAccepted():
            super(plotSpectrum, self).keyReleaseEvent(event)


    def mouseClickEvent(self, ev):
        if ev.button() == Qt.RightButton and self.menuEnabled():
            ev.accept()
            self.raiseContextMenu(ev)

    def mousePressEvent(self, event):
        super(plotSpectrum, self).mousePressEvent(event)

        self.mousePoint_saved = self.vb.mapSceneToView(event.pos())
        if self.r_status:
            self.r_status == 2
            self.regions.add()

    def mouseReleaseEvent(self, event):
        if any([getattr(self, s+'_status') for s in 'abcdrsuwx']):
            self.vb.setMouseMode(self.vb.PanMode)
            self.vb.rbScaleBox.hide()
        else:
            if event.button() == Qt.RightButton and self.menuEnabled() and self.customMenu:
                if self.mousePoint == self.mousePoint_saved:
                    self.raiseContextMenu(event)
                    event.accept()

        if self.a_status:
            if self.mousePoint == self.mousePoint_saved:
                if self.parent.line_reper.name in self.parent.fit.sys[-1].sp:
                    self.parent.fit.addSys(self.parent.comp)
                    self.parent.fit.sys[-1].z.val = self.mousePoint.x() / self.parent.line_reper.l() - 1
                    self.parent.fit.sys[-1].zrange(200)
                    self.parent.comp = len(self.parent.fit.sys) - 1
                    try:
                        sys = fitModelSysWidget(self.parent.fitModel, len(self.parent.fitModel.fit.sys) - 1)
                        self.parent.fitModel.tab.addTab(sys, "sys {:}".format(self.parent.fitModel.tabNum + 1))
                        self.parent.fitModel.tab.setCurrentIndex(len(self.parent.fitModel.fit.sys) - 1)
                    except:
                        pass
                    self.parent.s.refreshFitComps()
                    self.parent.showFit(all=self.showfullfit)

        if self.b_status:
            if event.button() == Qt.LeftButton:
                if self.mousePoint == self.mousePoint_saved:
                    self.parent.s[self.parent.s.ind].add_spline(self.mousePoint.x(), self.mousePoint.y())
                else:
                    self.parent.s[self.parent.s.ind].del_spline(self.mousePoint_saved.x(), self.mousePoint_saved.y(), self.mousePoint.x(), self.mousePoint.y())

            if event.button() == Qt.RightButton:
                ind = self.parent.s[self.parent.s.ind].spline.find_nearest(self.mousePoint.x(), self.mousePoint.y())
                self.parent.s[self.parent.s.ind].del_spline(arg=ind)
                event.accept()

        if self.c_status:
            try:
                print('c_status:', self.parent.line_reper.name, self.parent.fit.sys[self.parent.comp].sp.keys())
                if self.parent.line_reper.name in self.parent.fit.sys[self.parent.comp].sp:
                    self.parent.fit.sys[self.parent.comp].z.set(self.mousePoint.x() / self.parent.line_reper.l() - 1)
                    if self.mousePoint.y() != self.mousePoint_saved.y():
                        sp = self.parent.fit.sys[self.parent.comp].sp[self.parent.line_reper.name]
                        # sp.b.set(sp.b.val + (self.mousePoint_saved.x() / self.mousePoint.x() - 1) * 299794.26)
                        sp.N.set(sp.N.val + np.sign(self.mousePoint_saved.y() - self.mousePoint.y()) * np.log10(
                                 1 + np.abs((self.mousePoint_saved.y() - self.mousePoint.y()) / 0.1)))
                    try:
                        self.parent.fitModel.refresh()
                    except:
                        pass
                    self.c_status = 2
            except:
                pass

            self.parent.s.prepareFit(self.parent.comp, all=self.showfullfit)
            self.parent.s.calcFit(self.parent.comp, recalc=True, redraw=True)
            self.parent.s.calcFit(recalc=True, redraw=True)

        if self.h_status:
            self.parent.console.exec_command('show HI')
            self.parent.abs.redraw(z=self.mousePoint.x()/1215.6701 - 1)

        if self.i_status:
            self.parent.console.exec_command('show HI')
            self.parent.abs.redraw(z=self.mousePoint.x() / 1215.6701 - 1)
            self.parent.s[self.parent.s.ind].mask.raw.x = np.zeros_like(self.parent.s[self.parent.s.ind].mask.raw.x)
            self.parent.s[self.parent.s.ind].mask.normalize(norm=True)
            self.parent.s[self.parent.s.ind].auto_select(self.mousePoint.x())
            self.parent.fit = fitPars(self.parent)
            self.parent.fit.addSys(z=self.mousePoint.x() / 1215.6701 - 1)
            self.parent.fit.sys[0].addSpecies('HI')
            self.parent.fit.sys[0].sp['HI'].b.set(1)
            self.parent.fit.sys[0].sp['HI'].b.vary = False
            self.parent.fit.sys[0].sp['HI'].N.set(14.5)
            self.parent.fit.add('res')
            self.parent.fit.res.set(7000)
            self.parent.fitLM()

        if self.p_status:
            self.doublet[self.p_status-1] = self.mousePoint
            if self.p_status == 2:
                self.add_pcRegion(self.doublet[0], self.doublet[1])
            self.p_status = 1 if self.p_status == 2 else 2

        if self.r_status:
            self.r_status = 1

        if self.s_status or self.d_status:
            for s in self.parent.s:
                #if QApplication.keyboardModifiers() == Qt.ShiftModifier or i == self.parent.s.ind:
                if QApplication.keyboardModifiers() == Qt.ShiftModifier or s.active():
                    s.add_points(self.mousePoint_saved.x(), self.mousePoint_saved.y(), self.mousePoint.x(), self.mousePoint.y(), remove=self.d_status, redraw=False)
                    #self.parent.s[i].add_points(self.mousePoint_saved.x(), self.mousePoint_saved.y(), self.mousePoint.x(), self.mousePoint.y(), remove=False)
                    s.set_fit_mask()
                    s.update_points()
                    s.set_res()
            self.parent.s.chi2()

        if self.u_status:
            if self.u_status == 1 and self.mousePoint.x() == self.mousePoint_saved.x() and self.mousePoint.y() == self.mousePoint_saved.y():
                if len(self.doublets) == 0 or self.doublets[-1].temp is None:
                    self.doublets.append(Doublet(self))
                    self.doublets[-1].draw_temp(self.mousePoint.x())
                else:
                    self.doublets[-1].find(self.doublets[-1].line_temp.value(), self.mousePoint.x())
                    self.doublets.update()
                    self.u_status = False
                #self.u_status += 1

        if self.w_status:
            s = self.parent.s[self.parent.s.ind]
            mask = np.logical_and(s.spec.x() > min(self.mousePoint.x(), self.mousePoint_saved.x()),
                                  s.spec.x() < max(self.mousePoint.x(), self.mousePoint_saved.x()))
            if np.sum(mask) > 0:
                x, y = s.spec.x()[mask], s.spec.y()[mask]
                curve1 = plotStepSpectrum(x=x, y=y, pen=pg.mkPen())
                x, y = curve1.returnPathData()
                if QApplication.keyboardModifiers() != Qt.ShiftModifier:
                    if self.parent.normview:
                        cont = interp1d(x, np.ones_like(x), fill_value=1)
                    else:
                        s.cont.interpolate()
                        cont = s.cont.inter
                else:
                    s.fit.interpolate()
                    cont = s.fit.inter
                curve2 = pg.PlotCurveItem(x=x, y=cont(x), pen=pg.mkPen())

                w = np.trapz(1.0 - y / cont(x), x=x)
                err_w =  np.sqrt(np.sum((s.spec.err()[mask] / cont(x)[:-1:2]  * np.diff(x)[::2])**2))
                print(w, err_w)
                self.w_region = pg.FillBetweenItem(curve1, curve2, brush=pg.mkBrush(44, 160, 44, 150))
                self.vb.addItem(self.w_region)
                self.w_label = pg.TextItem('w = {:0.5f}+/-{:0.5f}, log(w/l)={:0.2f}'.format(w, err_w, np.log10(2 * w / (x[0]+x[-1]))),  anchor=(0,1), color=(44, 160, 44))
                self.w_label.setFont(QFont("SansSerif", 14))
                #print('{:0.2f}'.format(w), (x[0]+x[-1])/2, s.cont.inter((x[0]+x[-1])/2))
                self.w_label.setPos((x[0]+x[-1])/2, cont((x[0]+x[-1])/2))
                self.vb.addItem(self.w_label)
        if self.x_status:
            self.parent.s[self.parent.s.ind].add_points(self.mousePoint_saved.x(), self.mousePoint_saved.y(), self.mousePoint.x(), self.mousePoint.y(), remove=(QApplication.keyboardModifiers() == Qt.ShiftModifier), bad=True)

        if event.isAccepted():
            super(plotSpectrum, self).mouseReleaseEvent(event)
            
    def mouseMoveEvent(self, event):
        super(plotSpectrum, self).mouseMoveEvent(event)
        self.mousePoint = self.vb.mapSceneToView(event.pos())
        self.mouse_moved = True
        self.cursorpos.setText('x={0:.3f}, y={1:.2f}, rest={2:.3f}'.format(self.mousePoint.x(), self.mousePoint.y(), self.mousePoint.x()/(1+self.parent.z_abs)))
        #self.cursorpos.setText("<span style='font-size: 12pt'>x={0:.3f}, <span style='color: red'>y={1:.2f}</span>".format(mousePoint.x(),mousePoint.y()))
        pos = self.vb.sceneBoundingRect()
        self.cursorpos.setPos(self.vb.mapSceneToView(QPoint(pos.left()+10,pos.bottom()-10)))
        self.specname.setPos(self.vb.mapSceneToView(QPoint(pos.right()-10,pos.bottom()-10)))
        if self.r_status == 2 and event.type() == QEvent.MouseMove:
            self.regions[-1].setRegion([self.mousePoint_saved.x(), self.mousePoint.x()])

        if (self.a_status or self.c_status) and event.type() == QEvent.MouseMove:
            self.vb.rbScaleBox.hide()


    def wheelEvent(self, event):
        if self.c_status:
            sp = self.parent.fit.sys[self.parent.comp].sp[self.parent.line_reper.name]
            sp.b.set(sp.b.val * np.power(1.2, np.sign(event.angleDelta().y())))
            self.parent.s.prepareFit(self.parent.comp, all=self.showfullfit)
            self.parent.s.calcFit(self.parent.comp, recalc=True, redraw=True)
            self.parent.s.calcFit(recalc=True, redraw=True)
            self.c_status = 2
            try:
                self.parent.fitModel.refresh()
            except:
                pass
            event.accept()
        elif self.m_status:
            #self.m_status =
            self.parent.s[self.parent.s.ind].rebinning(np.power(2.0, np.sign(event.angleDelta().y())))
        else:
            super(plotSpectrum, self).wheelEvent(event)
            pos = self.vb.sceneBoundingRect()
            self.cursorpos.setPos(self.vb.mapSceneToView(QPoint(pos.left()+10,pos.bottom()-10)))
            self.specname.setPos(self.vb.mapSceneToView(QPoint(pos.right()-10,pos.bottom()-10)))

    def mouseDragEvent(self, ev):
        
        if ev.button() == Qt.RightButton:
            ev.ignore()
        else:
            pg.ViewBox.mouseDragEvent(self, ev)
         
        ev.accept() 
        pos = ev.pos()
        
        if ev.button() == Qt.RightButton:
            self.updateScaleBox(ev.buttonDownPos(), ev.pos())
            
            if ev.isFinish():  
                self.rbScaleBox.hide()
                ax = QtCore.QRectF(Point(ev.buttonDownPos(ev.button())), Point(pos))
                ax = self.childGroup.mapRectFromParent(ax) 
                MouseRectCoords =  ax.getCoords()  
                self.dataSelection(MouseRectCoords)      
            else:
                self.updateScaleBox(ev.buttonDownPos(), ev.pos())

    def updateRegions(self):
        if len(self.regions) > 0:
            for r in self.regions:
                if not r.active:
                    pass
                    #print(r.size_full)
            self.parent.s.apply_regions()

    def add_line(self, x, y):
        if self.addline is not None:
            self.vb.removeItem(self.addline)
        self.addline = pg.PlotCurveItem(x=x, y=y, clickable=True)
        #self.add_line.sigClicked.connect(self.specClicked)
        self.addline.setPen(pg.mkPen(255, 69, 0, width=3))
        self.vb.addItem(self.addline)

    def add_doublet(self, x1, x2):
        self.doublets.append(Doublet(self))
        self.doublets[-1].find(x1, x2)

    def add_pcRegion(self, x1=None, x2=None):
        self.pcRegions.append(pcRegion(self, len(self.pcRegions), x1, x2))

    def remove_pcRegion(self, ind=None):
        if len(self.pcRegions) > 0:
            if ind is None:
                for p in reversed(self.pcRegions):
                    p.remove()
            elif isinstance(ind, int):
                self.pcRegions[ind].remove()

    def dataSelection(self,MouseRectCoords):
        print(MouseRectCoords)       

class residualsWidget(pg.PlotWidget):
    """
    class for plotting residual panel tighte with 1d spectrum panel
    """
    def __init__(self, parent):
        bottomaxis = pg.AxisItem(orientation='bottom')
        #stringaxis.setTickSpacing(minor=[(10, 0)])
        bottomaxis.setStyle(tickLength=-15, tickTextOffset=2)
        topaxis = pg.AxisItem(orientation='top')
        #topaxis.setStyle(tickLength=-15, tickTextOffset=2, stopAxisAtTick=(True, True))
        pg.PlotWidget.__init__(self, axisItems={'bottom': bottomaxis, 'top': topaxis}, background=(29,29,29))

        self.scene().removeItem(bottomaxis)
        self.parent = parent
        self.vb = self.getViewBox()
        self.vb.enableAutoRange(y=self.vb.YAxis)
        self.setXLink(self.parent.plot)
        self.addLines()

        # create new plot for kde and link its y axis
        if 0:
            self.kde = pg.PlotItem(axisItems={})
            self.kde.hideAxis('bottom')
            self.kde.setFixedHeight(300)
            self.kde.setFixedWidth(300)
        else:
            self.kde = pg.ViewBox()
            self.kde.setGeometry(self.vb.sceneBoundingRect())
            self.kde.setGeometry(QRectF(25.0, 1.0, 150.0, 458.0))
            print('residual:', self.vb.sceneBoundingRect())
        self.scene().addItem(self.kde)
        self.kde.setYLink(self)
        #self.getAxis('right').setLabel('axis2', color='#0000ff')

    def addLines(self):
        #self.addItem(pg.InfiniteLine(0.0, 0, pen=pg.mkPen(color=(100, 100, 100), width=1, style=Qt.DashLine)))
        self.region = pg.LinearRegionItem([-1, 1], orientation=pg.LinearRegionItem.Horizontal, brush=pg.mkBrush(182, 232, 182, 20))
        self.region.setMovable(False)
        for l in self.region.lines:
            l.setPen(pg.mkPen(None))
            l.setHoverPen(pg.mkPen(None))
        self.addItem(self.region)
        levels = [1,2,3]
        colors = [(100, 100, 100), (100, 100, 100), (100, 100, 100)]
        widths = [1.5, 1.0, 0.5]
        for l, color, width in zip(levels, colors, widths):
            self.addItem(pg.InfiniteLine(l, 0, pen=pg.mkPen(color=color, width=width, style=Qt.DashLine)))
            self.addItem(pg.InfiniteLine(-l, 0, pen=pg.mkPen(color=color, width=width, style=Qt.DashLine)))

    def viewRangeChanged(self, view, range):
        self.sigRangeChanged.emit(self, range)
        if len(self.parent.s) > 0:
            res = self.parent.s[self.parent.s.ind].res
            mask = np.logical_and(res.x > range[0][0], res.x < range[0][1])
            y = res.y[mask]
            if np.sum(mask) > 3 and not np.isnan(np.sum(y)) and not np.isinf(np.sum(y)):
                kde = gaussian_kde(y)
                kde_x = np.linspace(np.min(y) - 1, np.max(y) + 1, int((np.max(y) - np.min(y))/0.1))
                self.parent.s[self.parent.s.ind].kde_local.setData(x=-kde_x, y=kde.evaluate(kde_x))


class spec2dWidget(pg.PlotWidget):
    """
    class for plotting 2d spectrum panel tight with 1d spectrum panel
    """
    def __init__(self, parent):
        bottomaxis = pg.AxisItem(orientation='bottom')
        #stringaxis.setTickSpacing(minor=[(10, 0)])
        bottomaxis.setStyle(tickLength=-15, tickTextOffset=2)
        topaxis = pg.AxisItem(orientation='top')
        #topaxis.setStyle(tickLength=-15, tickTextOffset=2, stopAxisAtTick=(True, True))
        pg.PlotWidget.__init__(self, axisItems={'bottom': bottomaxis, 'top': topaxis}, background=(29,29,29))

        self.initstatus()

        self.scene().removeItem(bottomaxis)
        self.parent = parent
        self.vb = self.getViewBox()
        self.vb.enableAutoRange(y=self.vb.YAxis)
        self.setXLink(self.parent.plot)
        self.vb.setMenuEnabled(False)
        #self.addLines()

        self.slits = []
        self.cursorpos = pg.TextItem(anchor=(0, 1), fill=pg.mkBrush(0, 0, 0, 0.5))
        self.vb.addItem(self.cursorpos, ignoreBounds=True)

        #self.getAxis('right').setLabel('axis2', color='#0000ff')

    def initstatus(self):
        self.b_status = False
        self.e_status = False
        self.r_status = False
        self.s_status = False
        self.t_status = False
        self.q_status = False
        self.x_status = False
        self.mouse_moved = False

    def addLines(self):
        # self.addItem(pg.InfiniteLine(0.0, 0, pen=pg.mkPen(color=(100, 100, 100), width=1, style=Qt.DashLine)))
        self.region = pg.LinearRegionItem([-1, 1], orientation=pg.LinearRegionItem.Horizontal,
                                          brush=pg.mkBrush(182, 232, 182, 20))
        self.region.setMovable(False)
        for l in self.region.lines:
            l.setPen(pg.mkPen(None))
            l.setHoverPen(pg.mkPen(None))
        self.addItem(self.region)
        levels = [1, 2, 3]
        colors = [(100, 100, 100), (100, 100, 100), (100, 100, 100)]
        widths = [1.5, 1.0, 0.5]
        for l, color, width in zip(levels, colors, widths):
            self.addItem(pg.InfiniteLine(l, 0, pen=pg.mkPen(color=color, width=width, style=Qt.DashLine)))
            self.addItem(pg.InfiniteLine(-l, 0, pen=pg.mkPen(color=color, width=width, style=Qt.DashLine)))

    def viewRangeChanged(self, view, range):
        self.sigRangeChanged.emit(self, range)

    def keyPressEvent(self, event):
        super(spec2dWidget, self).keyPressEvent(event)
        key = event.key()

        if not event.isAutoRepeat():

            if event.key() == Qt.Key_Down or event.key() == Qt.Key_Right:
                if self.e_status:
                    self.parent.s.setSpec(self.parent.s.ind + 1)

            if event.key() == Qt.Key_Up or event.key() == Qt.Key_Left:
                if self.e_status:
                    self.parent.s.setSpec(self.parent.s.ind - 1)

            if event.key() == Qt.Key_B:
                self.vb.setMouseMode(self.vb.RectMode)
                self.b_status = True
                self.mouse_moved = False

            if event.key() == Qt.Key_E:
                if (QApplication.keyboardModifiers() == Qt.ControlModifier):
                    self.parent.s.remove(self.parent.s.ind)
                else:
                    self.e_status = True
                    if self.parent.s[self.parent.s.ind].err2d is not None:
                        self.parent.s[self.parent.s.ind].err2d.setLevels(self.parent.s[self.parent.s.ind].spec2d.raw.err_levels)
                        self.vb.addItem(self.parent.s[self.parent.s.ind].err2d)

            if event.key() == Qt.Key_M:
                if self.parent.s[self.parent.s.ind].mask2d is not None:
                    self.vb.addItem(self.parent.s[self.parent.s.ind].mask2d)

            if event.key() == Qt.Key_R:
                self.r_status = True
                self.vb.setMouseMode(self.vb.RectMode)

            if event.key() == Qt.Key_S:
                self.s_status = True
                self.vb.setMouseEnabled(x=False, y=False)

            if event.key() == Qt.Key_T:
                self.t_status = True
                self.vb.setMouseMode(self.vb.RectMode)
                if (QApplication.keyboardModifiers() == Qt.ControlModifier):
                    for s in self.slits:
                        self.vb.removeItem(s[0])
                        self.vb.removeItem(s[1])
                    self.slits = []

            if event.key() == Qt.Key_Q:
                self.q_status = True
                if self.parent.s[self.parent.s.ind].sky2d is not None:
                    self.parent.s[self.parent.s.ind].sky2d.setLevels(self.parent.s[self.parent.s.ind].spec2d.sky.z_levels)
                    self.vb.addItem(self.parent.s[self.parent.s.ind].sky2d)

            if event.key() == Qt.Key_X:
                self.x_status = True
                self.vb.setMouseMode(self.vb.RectMode)
                s = self.parent.s[self.parent.s.ind].spec2d
                if s.cr is None:
                    s.cr = image(x=s.raw.x, y=s.raw.y, mask=np.zeros_like(s.raw.z))
                if (QApplication.keyboardModifiers() == Qt.ShiftModifier):
                    self.vb.removeItem(self.parent.s[self.parent.s.ind].cr_mask2d)


    def keyReleaseEvent(self, event):
        #super(spec2dWidget, self).keyReleaseEvent(event)

        if not event.isAutoRepeat():

            if event.key() == Qt.Key_B:
                self.b_status = False
                if not self.mouse_moved:
                    self.parent.s[self.parent.s.ind].add_spline(self.mousePoint.x(), self.mousePoint.y(), name='2d')
                print('keyRelease', self.b_status)

            if event.key() == Qt.Key_E:
                self.e_status = False
                print(self.parent.s[self.parent.s.ind].err2d)
                if self.parent.s[self.parent.s.ind].err2d is not None:
                    self.vb.removeItem(self.parent.s[self.parent.s.ind].err2d)

            if event.key() == Qt.Key_M:
                if self.parent.s[self.parent.s.ind].mask2d is not None:
                    self.vb.removeItem(self.parent.s[self.parent.s.ind].mask2d)

            if event.key() == Qt.Key_R:
                self.r_status = False

            if event.key() == Qt.Key_S:
                self.s_status = False

            if event.key() == Qt.Key_T:
                self.t_status = False

            if event.key() == Qt.Key_Q:
                self.q_status = False
                if self.parent.s[self.parent.s.ind].sky2d is not None:
                    self.vb.removeItem(self.parent.s[self.parent.s.ind].sky2d)

            if event.key() == Qt.Key_X:
                self.x_status = False
                #self.vb.addItem(self.parent.s[self.parent.s.ind].cr_mask2d)
                self.parent.s.redraw()


            if any([event.key() == getattr(Qt, 'Key_'+s) for s in ['S']]):
                self.vb.setMouseEnabled(x=True, y=True)

            if any([event.key() == getattr(Qt, 'Key_' + s) for s in 'BRSTX']):
                self.vb.setMouseMode(self.vb.PanMode)
                self.parent.statusBar.setText('')

        if event.isAccepted():
            super(spec2dWidget, self).keyReleaseEvent(event)


    def mousePressEvent(self, event):
        super(spec2dWidget, self).mousePressEvent(event)
        if self.s_status:
            self.s_status = 2

        if any([getattr(self, s + '_status') for s in 'brtsx']):
            self.mousePoint_saved = self.vb.mapSceneToView(event.pos())

        if self.t_status:
            self.t_status = 1

        if self.q_status:
            self.q_status = False
            self.mousePoint = self.vb.mapSceneToView(event.pos())
            s = self.parent.s[self.parent.s.ind].spec2d
            x = s.raw.x[np.argmin(np.abs(self.mousePoint.x() - s.raw.x))]
            if self.parent.extract2dwindow is not None:
                border = self.parent.extract2dwindow.extr_border
                poly = self.parent.extract2dwindow.sky_poly
                model = self.parent.extract2dwindow.skymodeltype
                conf = self.parent.extract2dwindow.extr_conf
            else:
                border, poly, model, conf = 5, 3, 'median', 0.03
            s.sky_model(x, x, border=border, poly=poly, model=model, conf=conf, plot=1, smooth=0)
            self.parent.spec2dPanel.vb.removeItem(s.parent.sky2d)
            s.parent.sky2d = s.set_image('sky', s.parent.colormap)
            self.parent.spec2dPanel.vb.addItem(s.parent.sky2d)

        if self.x_status:
            self.parent.s[self.parent.s.ind].spec2d.raw.add_mask(
                rect=[[np.min([self.mousePoint_saved.x(), self.mousePoint_saved.x()]),
                       np.max([self.mousePoint_saved.x(), self.mousePoint_saved.x()])],
                      [np.min([self.mousePoint_saved.y(), self.mousePoint_saved.y()]),
                       np.max([self.mousePoint_saved.y(), self.mousePoint_saved.y()])]
                      ], add=(QApplication.keyboardModifiers() != Qt.ControlModifier))
            self.parent.spec2dPanel.vb.removeItem(self.parent.s[self.parent.s.ind].cr_mask2d)
            self.parent.s[self.parent.s.ind].cr_mask2d = self.parent.s[self.parent.s.ind].spec2d.set_image('cr', self.parent.s[self.parent.s.ind].cr_maskcolormap)
            self.parent.spec2dPanel.vb.addItem(self.parent.s[self.parent.s.ind].cr_mask2d)

    def mouseReleaseEvent(self, event):
        if any([getattr(self, s+'_status') for s in 'brtx']):
            self.vb.setMouseMode(self.vb.PanMode)
            self.vb.rbScaleBox.hide()

        if any([getattr(self, s + '_status') for s in 's']):
            self.mousePoint_saved = self.vb.mapSceneToView(event.pos())

        if self.b_status:
            if event.button() == Qt.LeftButton:
                if self.mousePoint == self.mousePoint_saved:
                    self.parent.s[self.parent.s.ind].add_spline(self.mousePoint.x(), self.mousePoint.y(), name='2d')
                else:
                    self.parent.s[self.parent.s.ind].del_spline(self.mousePoint_saved.x(), self.mousePoint_saved.y(),
                                                                self.mousePoint.x(), self.mousePoint.y(), name='2d')

            if event.button() == Qt.RightButton:
                ind = self.parent.s[self.parent.s.ind].spline2d.find_nearest(self.mousePoint.x(), self.mousePoint.y())
                self.parent.s[self.parent.s.ind].del_spline(arg=ind, name='2d')
                event.accept()

        if self.t_status:
            self.mousePoint = self.vb.mapSceneToView(event.pos())

            if self.t_status == 1:
                spec2d = self.parent.s[self.parent.s.ind].spec2d
                if len(spec2d.slits) > 0:
                    data = np.asarray([[s[0], s[1]] for s in spec2d.slits])
                    print(data)
                    ind = np.argmin(np.sum((data - np.array([self.mousePoint.x(), self.mousePoint.y()]))**2, axis=1))
                    spec2d.slits.remove(spec2d.slits[ind])
                self.parent.s[self.parent.s.ind].redraw()

            if self.t_status == 2:
                self.t_status = False
                self.parent.s[self.parent.s.ind].spec2d.profile(np.min([self.mousePoint_saved.x(), self.mousePoint.x()]),
                                                                np.max([self.mousePoint_saved.x(), self.mousePoint.x()]),
                                                                np.min([self.mousePoint_saved.y(), self.mousePoint.y()]),
                                                                np.max([self.mousePoint_saved.y(), self.mousePoint.y()]),
                                                                plot=True)

        if self.x_status:
            self.parent.s[self.parent.s.ind].spec2d.cr.add_mask(
                rect=[[np.min([self.mousePoint_saved.x(), self.mousePoint.x()]),
                       np.max([self.mousePoint_saved.x(), self.mousePoint.x()])],
                      [np.min([self.mousePoint_saved.y(), self.mousePoint.y()]),
                       np.max([self.mousePoint_saved.y(), self.mousePoint.y()])]
                      ], add=(QApplication.keyboardModifiers() != Qt.ControlModifier))
            #self.parent.s.redraw()

        if event.isAccepted():
            super(spec2dWidget, self).mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        super(spec2dWidget, self).mouseMoveEvent(event)
        self.mousePoint = self.vb.mapSceneToView(event.pos())
        self.mouse_moved = True
        s = 'x={0:.3f}, y={1:.2f}'.format(self.mousePoint.x(), self.mousePoint.y())
        if len(self.parent.s) > 0 and self.parent.s[self.parent.s.ind].spec2d.raw.z is not None and len(self.parent.s[self.parent.s.ind].spec2d.raw.z.shape) == 2:
            s += ', z={:.2e}'.format(self.parent.s[self.parent.s.ind].spec2d.raw.find_nearest(self.mousePoint.x(), self.mousePoint.y()))
            if self.parent.s[self.parent.s.ind].spec2d.raw.err is not None:
                s += ', err={:.2e}'.format(self.parent.s[self.parent.s.ind].spec2d.raw.find_nearest(self.mousePoint.x(), self.mousePoint.y(), attr='err'))
        self.cursorpos.setText(s)

        pos = self.vb.sceneBoundingRect()
        self.cursorpos.setPos(self.vb.mapSceneToView(QPoint(pos.left() + 10, pos.bottom() - 10)))
        if self.s_status == 2 and event.type() == QEvent.MouseMove:
            range = self.vb.getState()['viewRange']
            delta = ((self.mousePoint.x() - self.mousePoint_saved.x()) / (range[0][1] - range[0][0]),
                     (self.mousePoint.y() - self.mousePoint_saved.y()) / (range[1][1] - range[1][0]))
            self.mousePoint_saved = self.mousePoint
            im = self.parent.s[self.parent.s.ind].image2d
            levels = im.getLevels()
            d = self.parent.s[self.parent.s.ind].spec2d.raw.z_quantile[1] - self.parent.s[self.parent.s.ind].spec2d.raw.z_quantile[0]
            self.parent.s[self.parent.s.ind].spec2d.raw.setLevels(levels[0] + d*delta[0]*2, levels[1] + d*delta[1]/4)
            im.setLevels(self.parent.s[self.parent.s.ind].spec2d.raw.z_levels)

        if self.t_status:
            self.t_status = 2

        if self.s_status and event.type() == QEvent.MouseMove:
            self.vb.rbScaleBox.hide()


    def wheelEvent(self, event):
        super(spec2dWidget, self).wheelEvent(event)
        pos = self.vb.sceneBoundingRect()
        self.cursorpos.setPos(self.vb.mapSceneToView(QPoint(pos.left() + 10, pos.bottom() - 10)))

    def mouseDragEvent(self, ev):

        if ev.button() == Qt.RightButton:
            ev.ignore()
        else:
            pg.ViewBox.mouseDragEvent(self, ev)

        ev.accept()
        pos = ev.pos()

        if ev.button() == Qt.RightButton:
            self.updateScaleBox(ev.buttonDownPos(), ev.pos())

            if ev.isFinish():
                self.rbScaleBox.hide()
                ax = QtCore.QRectF(Point(ev.buttonDownPos(ev.button())), Point(pos))
                ax = self.childGroup.mapRectFromParent(ax)
                MouseRectCoords = ax.getCoords()
                self.dataSelection(MouseRectCoords)
            else:
                self.updateScaleBox(ev.buttonDownPos(), ev.pos())

class preferencesWidget(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.move(200,100)
        self.setWindowTitle('Preferences')
        self.setStyleSheet(open('config/styles.ini').read())

        self.initGUI()
        self.setGeometry(300, 200, 100, 100)
        self.show()

    def initGUI(self):
        layout = QVBoxLayout()

        self.tab = QTabWidget()
        self.tab.setGeometry(0, 0, 1050, 900)
        #self.tab.setMinimumSize(1050, 300)
        
        for t in ['Appearance', 'Fit', 'Colors']:
            self.tab.addTab(self.initTabGUI(t), t)

        layout.addWidget(self.tab)
        h = QHBoxLayout()
        h.addStretch(1)
        ok = QPushButton("Ok")
        ok.setFixedSize(110, 30)
        ok.clicked.connect(self.close)
        h.addWidget(ok)
        layout.addStretch(1)
        layout.addLayout(h)
        self.setLayout(layout)


    def initTabGUI(self, window=None):

        frame = QFrame()
        validator = QDoubleValidator()
        locale = QLocale('C')
        validator.setLocale(locale)

        layout = QHBoxLayout()
        self.grid = QGridLayout()

        if window == 'Fit':

            ind = 0
            self.fitGroup = QButtonGroup(self)
            self.fittype = ['regular', 'fft', 'fast']
            for i, f in enumerate(self.fittype):
                s = ':' if f == 'fast' else ''
                setattr(self, f, QRadioButton(f + s))
                getattr(self, f).toggled.connect(self.setFitType)
                self.fitGroup.addButton(getattr(self, f))
                self.grid.addWidget(getattr(self, f), ind, i)
            getattr(self, self.parent.fitType).toggle()

            self.num_between = QLineEdit(str(self.parent.num_between))
            self.num_between.setValidator(validator)
            self.num_between.textChanged[str].connect(self.setNumBetween)
            self.grid.addWidget(self.num_between, ind, 3)

            ind += 1
            self.grid.addWidget(QLabel('Tau limit:'), ind, 0)

            self.tau_limit = QLineEdit(str(self.parent.tau_limit))
            self.tau_limit.setValidator(validator)
            self.tau_limit.textChanged[str].connect(self.setTauLimit)
            self.grid.addWidget(self.tau_limit, ind, 1)

            ind += 1
            self.grid.addWidget(QLabel('fit components:'), ind, 0)
            self.compGroup = QButtonGroup(self)
            self.compview = ['all', 'one', 'none']
            for i, f in enumerate(self.compview):
                setattr(self, f, QRadioButton(f))
                getattr(self, f).toggled.connect(self.setCompView)
                self.compGroup.addButton(getattr(self, f))
                self.grid.addWidget(getattr(self, f), ind, i+1)
            getattr(self, self.parent.comp_view).toggle()

            ind += 1
            self.fitPoints = QCheckBox('show fit points')
            self.fitPoints.setChecked(self.parent.fitPoints)
            self.fitPoints.stateChanged.connect(partial(self.setChecked, 'fitPoints'))
            self.grid.addWidget(self.fitPoints, ind, 0)

            ind +=1
            self.animateFit = QCheckBox('animate fit')
            self.animateFit.setChecked(self.parent.animateFit)
            self.animateFit.stateChanged.connect(partial(self.setChecked, 'animateFit'))
            self.grid.addWidget(self.animateFit, ind, 0)

        if window == 'Appearance':
            ind = 0
            self.grid.addWidget(QLabel('Spectrum view:'), ind, 0)
            self.specview = QComboBox()
            self.viewdict = OrderedDict([('step', 'step'), ('steperr', 'step + err'), ('line', 'lines'),
                                         ('lineerr', 'lines + err'), ('point', 'points'), ('pointerr', 'points + err')])
            self.specview.addItems(list(self.viewdict.values()))
            self.specview.setCurrentText(self.viewdict[self.parent.specview])
            self.specview.currentIndexChanged.connect(self.setSpecview)
            self.specview.setFixedSize(120, 30)
            self.grid.addWidget(self.specview, ind, 1)

            ind += 1
            self.grid.addWidget(QLabel('Fitting points view:'), ind, 0)
            self.selectview = QComboBox()
            self.selectview.addItems(['point', 'color', 'region'])
            self.selectview.setCurrentText(self.parent.selectview)
            self.selectview.currentIndexChanged.connect(self.setSelect)
            self.selectview.setFixedSize(120, 30)
            self.grid.addWidget(self.selectview, ind, 1)

            ind += 1
            self.grid.addWidget(QLabel('Line labels view:'), ind, 0)
            self.selectlines = QComboBox()
            self.selectlines.addItems(['short', 'infinite'])
            self.selectlines.setCurrentText(self.parent.linelabels)
            self.selectlines.currentIndexChanged.connect(self.setLabels)
            self.selectlines.setFixedSize(120, 30)
            self.grid.addWidget(self.selectlines, ind, 1)

            ind += 1
            self.showinactive = QCheckBox('show inactive exps')
            self.showinactive.setChecked(self.parent.showinactive)
            self.showinactive.stateChanged.connect(partial(self.setChecked, 'showinactive'))
            self.grid.addWidget(self.showinactive, ind, 0)

            ind += 1
            self.show_osc = QCheckBox('f in line labels')
            self.show_osc.setChecked(self.parent.show_osc)
            self.show_osc.stateChanged.connect(partial(self.setChecked, 'show_osc'))
            self.grid.addWidget(self.show_osc, ind, 0)

        layout.addLayout(self.grid)
        layout.addStretch()
        frame.setLayout(layout)
        return frame

    def setSpecview(self):
        self.parent.specview = list(self.viewdict.keys())[list(self.viewdict.values()).index(self.specview.currentText())]
        self.parent.options('specview', self.parent.specview)
        if self.parent.s.ind is not None:
            self.parent.s[self.parent.s.ind].remove()
            self.parent.s[self.parent.s.ind].init_GU()

    def setSelect(self):
        if self.parent.s.ind is not None:
            self.parent.s[self.parent.s.ind].remove()
        self.parent.selectview = self.selectview.currentText()
        self.parent.options('selectview', self.parent.selectview)
        if self.parent.s.ind is not None:
            self.parent.s[self.parent.s.ind].init_GU()

    def setLabels(self):
        self.parent.linelabels = self.selectlines.currentText()
        self.parent.options('linelabels', self.parent.linelabels)
        self.parent.abs.changeStyle()

    def setFitType(self):
        for f in self.fittype:
            if getattr(self, f).isChecked():
                self.parent.fitType = f.replace(':', '')
                self.parent.options('fitType', self.parent.fitType)
                return

    def setCompView(self):
        for f in self.compview:
            if getattr(self, f).isChecked():
                self.parent.comp_view = f
                self.parent.options('comp_view', self.parent.comp_view)
                self.parent.s.redraw()
                return

    def setChecked(self, attr):
        self.parent.options(attr, getattr(self, attr).isChecked())
        if attr == 'show_osc':
            self.parent.abs.redraw()
        self.parent.s.redraw()

    def setNumBetween(self):
        self.parent.num_between = int(self.num_between.text())
        self.parent.options('num_between', self.parent.num_between)

    def setTauLimit(self):
        try:
            t = float(self.tau_limit.text())
            if t < 1 and t > 0:
                self.parent.tau_limit = t
                self.parent.options('tau_limit', self.parent.tau_limit)
        except:
            pass

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F11:
            self.close()

    def closeEvent(self, event):
        self.parent.preferences = None
        event.accept()

class showLinesWidget(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.resize(800, 700)
        self.move(200, 100)
        #self.setWindowFlags(Qt.FramelessWindowHint)

        self.initData()
        self.initGUI()
        self.setWindowTitle('Plot lines using Matploplib')
        self.setStyleSheet(open('config/styles.ini').read())

    def initData(self):
        self.savedText = None
        self.opts = OrderedDict([
                    ('width', float), ('height', float),
                    ('rows', int), ('cols', int), ('order', str),
                    ('v_indent', float), ('h_indent', float),
                    ('col_offset', float), ('row_offset', float),
                    ('units', str), ('regions', int),
                    ('xmin', float), ('xmax', float), ('ymin', float), ('ymax', float),
                    ('residuals', int), ('gray_out', int), ('res_sigma', int),
                    ('show_comps', int), ('fit_lw', float), ('sys_ind', int),
                    ('font', int), ('xlabel', str), ('ylabel', str),
                    ('x_ticks', float), ('xnum', int), ('y_ticks', float), ('ynum', int),
                    ('font_labels', int), ('name_x_pos', float), ('name_y_pos', float),
                    ('plotfile', str), ('show_cont', int), ('show_H2', str), ('pos_H2', float),
                    ('show_cf', int),
                    ])
        for opt, func in self.opts.items():
            #print(opt, self.parent.options(opt), func(self.parent.options(opt)))
            setattr(self, opt, func(self.parent.options(opt)))

        self.y_formatter = None

    def initGUI(self):
        hlayout = QHBoxLayout()
        self.setLayout(hlayout)
        layout = QVBoxLayout()
        hlayout.addLayout(layout)
        hlayout.addStretch(1)
        l = QVBoxLayout()
        l1 = QHBoxLayout()
        self.numLines = QPushButton('Lines: '+str(len(self.parent.lines)))
        self.numLines.setCheckable(True)
        self.numLines.setFixedSize(110, 25)
        self.numLines.clicked.connect(partial(self.changeState, 'lines'))
        self.numRegions = QPushButton('Region: '+str(len(self.parent.plot.regions)))
        self.numRegions.setCheckable(True)
        self.numRegions.setFixedSize(110, 25)
        self.numRegions.clicked.connect(partial(self.changeState, 'regions'))
        l1.addWidget(self.numLines)
        l1.addStretch(1)
        l1.addWidget(self.numRegions)
        l.addLayout(l1)
        self.lines = QTextEdit()
        self.setLines(init=True)
        self.lines.setFixedSize(240, self.frameGeometry().height())
        self.lines.textChanged.connect(self.readLines)
        l.addWidget(self.lines)
        self.chooseLine = QComboBox()
        self.chooseLine.setFixedSize(130, 30)
        self.chooseLine.addItems(['choose...'] + [str(l.line) for l in self.parent.abs.lines])
        self.chooseLine.activated[str].connect(self.selectLine)
        l.addWidget(self.chooseLine)
        hlayout.addLayout(l)

        grid = QGridLayout()
        layout.addLayout(grid)
        validator = QDoubleValidator()
        locale = QLocale('C')
        validator.setLocale(locale)
        #validator.ScientificNotation
        names = ['Size:', 'width:', '', 'height:', '',
                 'Panels:', 'cols:', '', 'rows:', '',
                 'Indents:', 'hor.:', '', 'vert.:', '',
                 'Order', '', '', '', '',
                 '0ffets between:', 'col:', '', 'row:', '',
                 'X-units:', '', '', '', '',
                 'X-scale:', 'min:', '', 'max:', '',
                 'Y-scale:', 'min:', '', 'max:', '',
                 'Residuals:', '', '', 'sig:', '',
                 'Comps:', '', '', 'central:', '',
                 'Fonts:', 'axis:', '', '', '',
                 'Labels:', 'x:', '', 'y:', '',
                 'X-ticks:', 'scale:', '', 'num', '',
                 'Y-ticks:', 'scale:', '', 'num', '',
                 'Line labels:', 'font:', '', '', '',
                 '', 'hor.:', '', 'vert.:', '',
                 'Continuum', '', '', '', '',
                 'H2:', '', '', 'pos:', '',
                 'Covering factor:', '', '', '', '',]

        positions = [(i, j) for i in range(19) for j in range(5)]

        for position, name in zip(positions, names):
            if name == '':
                continue
            grid.addWidget(QLabel(name), *position)

        self.opt_but = OrderedDict([('width', [0, 2]), ('height', [0, 4]), ('cols', [1, 2]), ('rows', [1, 4]),
                                    ('v_indent', [2, 2]), ('h_indent', [2, 4]), ('col_offset', [4, 2]), ('row_offset', [4, 4]),
                                    ('xmin', [6, 2]), ('xmax', [6, 4]), ('ymin', [7, 2]), ('ymax', [7, 4]),
                                    ('res_sigma', [8, 4]), ('fit_lw', [9, 2]), ('font', [10, 2]),
                                    ('xlabel', [11, 2]), ('ylabel', [11, 4]),
                                    ('x_ticks', [12, 2]), ('xnum', [12, 4]), ('y_ticks', [13, 2]), ('ynum', [13, 4]),
                                    ('font_labels', [14, 2]), ('name_x_pos', [15, 2]), ('name_y_pos', [15, 4]),
                                    ('show_H2', [17, 2]), ('pos_H2', [17, 4])])
        for opt, v in self.opt_but.items():
            b = QLineEdit(str(getattr(self, opt)))
            b.setFixedSize(80, 30)
            if opt not in ['xlabel', 'ylabel', 'show_H2']:
                b.setValidator(validator)
            b.textChanged[str].connect(partial(self.onChanged, attr=opt))
            grid.addWidget(b, v[0], v[1])

        self.orderh = QCheckBox("hor.", self)
        self.orderh.clicked.connect(partial(self.setOrder, 'h'))
        self.orderv = QCheckBox("vert.", self)
        self.orderv.clicked.connect(partial(self.setOrder, 'v'))
        self.setOrder(self.order)
        grid.addWidget(self.orderh, 3, 2)
        grid.addWidget(self.orderv, 3, 4)

        self.unitsv = QCheckBox("vel.", self)
        self.unitsv.clicked.connect(partial(self.setUnits, 'v'))
        self.unitsl = QCheckBox("lambda", self)
        self.unitsl.clicked.connect(partial(self.setUnits, 'l'))
        self.setUnits(self.units)
        grid.addWidget(self.unitsv, 5, 2)
        grid.addWidget(self.unitsl, 5, 4)

        self.resid = QCheckBox('')
        self.resid.setChecked(self.residuals)
        self.resid.clicked[bool].connect(self.setResidual)
        grid.addWidget(self.resid, 8, 1)

        self.gray = QCheckBox('gray')
        self.gray.setChecked(self.gray_out)
        self.gray.clicked[bool].connect(self.setGray)
        grid.addWidget(self.gray, 8, 2)

        self.plotcomps = QCheckBox('show')
        self.plotcomps.setChecked(self.show_comps)
        self.plotcomps.clicked[bool].connect(self.setPlotComps)
        grid.addWidget(self.plotcomps, 9, 1)

        self.refcomp = QComboBox(self)
        self.refcomp.addItems([str(i+1) for i in range(len(self.parent.fit.sys))])
        self.sys_ind = min(self.sys_ind, len(self.parent.fit.sys))
        self.refcomp.setCurrentIndex(self.sys_ind-1)
        self.refcomp.currentIndexChanged.connect(self.onIndChoose)
        grid.addWidget(self.refcomp, 9, 4)

        self.showcont = QCheckBox('show')
        self.showcont.setChecked(self.show_cont)
        self.showcont.clicked[bool].connect(self.setCont)
        grid.addWidget(self.showcont, 16, 1)

        self.showcf = QCheckBox('show')
        self.showcf.setChecked(self.show_cf)
        self.showcf.clicked[bool].connect(self.setCf)
        grid.addWidget(self.showcf, 18, 1)

        layout.addStretch(1)
        l = QHBoxLayout()
        self.showButton = QPushButton("Show")
        self.showButton.setFixedSize(110, 30)
        self.showButton.clicked.connect(partial(self.showPlot, False, []))
        expButton = QPushButton("Export")
        expButton.setFixedSize(110, 30)
        expButton.clicked.connect(partial(self.showPlot, True, []))
        self.file = QLineEdit(self.plotfile)
        self.file.setFixedSize(350, 30)
        self.file.textChanged[str].connect(self.setFilename)

        l.addWidget(self.showButton)
        l.addWidget(expButton)
        l.addWidget(self.file)
        l.addStretch(1)
        layout.addLayout(l)

        l = QHBoxLayout()
        save = QPushButton("Save Settings")
        save.setFixedSize(150, 30)
        save.clicked.connect(self.saveSettings)
        load = QPushButton("Load Settings")
        load.setFixedSize(150, 30)
        load.clicked.connect(partial(self.loadSettings, None))
        l.addWidget(save)
        l.addWidget(load)
        l.addStretch(1)
        layout.addLayout(l)

        self.changeState()

    def onChanged(self, text, attr=None):
        if attr is not None:
            setattr(self, attr, self.opts[attr](text))

    def setLines(self, init=False):
        if self.regions:
            self.lines.setText(str(self.parent.plot.regions))
        else:
            self.lines.setText(str(self.parent.lines))
        self.readLines()

    def changeState(self, s=None):
        if s == 'lines' and self.regions or s == 'regions' and not self.regions:
            if s == 'lines':
                self.regions = False
            if s == 'regions':
                self.regions = True
            text = self.lines.toPlainText()
            if self.savedText is None:
                self.setLines(init=True)
            else:
                self.lines.setText(self.savedText)
            self.savedText = text
            self.readLines()
        self.chooseLine.clear()
        if self.regions:
            self.chooseLine.addItems(['choose...'] + [str(p) for p in self.parent.plot.regions])
        else:
            self.chooseLine.addItems(['choose...'] + [str(l.line) for l in self.parent.abs.lines])
        self.numLines.setChecked(not self.regions)
        self.numRegions.setChecked(self.regions)

    def setOrder(self, s):
        for o in ['v', 'h']:
            getattr(self, 'order'+o).setChecked(s == o)
        self.order = s

    def setUnits(self, s):
        for u in ['v', 'l']:
            getattr(self, 'units'+u).setChecked(s == u)
        self.units = s

    def setResidual(self, b):
        self.residuals = int(self.resid.isChecked())

    def setGray(self, b):
        self.gray_out = int(self.gray.isChecked())

    def setPlotComps(self, b):
        self.show_comps = int(self.plotcomps.isChecked())

    def setCf(self, b):
        self.show_cf = int(self.showcf.isChecked())

    def setCont(self, b):
        self.show_cont = int(self.showcont.isChecked())

    def setFilename(self):
        self.plotfile = self.file.text()

    def readLines(self):
        if self.regions:
            self.parent.plot.regions.fromText(self.lines.toPlainText(), sort=False)
            self.numRegions.setText('Regions: ' + str(len(self.parent.plot.regions)))
        else:
            self.parent.lines.fromText(self.lines.toPlainText())
            self.numLines.setText('Lines: '+str(len(self.parent.lines)))

    def selectLine(self, line):
        if self.regions:
            if line not in self.parent.regions:
                self.parent.regions.append(line)
                self.lines.setText(self.lines.toPlainText() + '\n' + line)
        else:
            if line not in self.parent.lines:
                self.parent.lines.append(line)
                self.lines.setText(self.lines.toPlainText()+ '\n'+line)
        self.chooseLine.setCurrentIndex(0)

    def onIndChoose(self):
        self.sys_ind = self.refcomp.currentIndex() + 1

    def showPlot(self, savefig=True, showH2=[]):
        fig = plt.figure(figsize=(self.width, self.height), dpi=300)
        #self.subplot = self.mw.getFigure().add_subplot(self.rows, self.cols, 1)

        if not self.regions:
            if not self.parent.normview:
                self.parent.normalize()

            self.ps = plot_spec(len(self.parent.lines), font=self.font, font_labels=self.font_labels,
                           vel_scale=(self.units=='l'), gray_out=self.gray_out, figure=fig)
            rects = rect_param(n_rows=int(self.rows), n_cols=int(self.cols), order=self.order,
                               v_indent=self.v_indent, h_indent=self.h_indent,
                               col_offset=self.col_offset, row_offset=self.row_offset)
            self.ps.specify_rects(rects)
            self.ps.set_ticklabels()
            self.ps.set_limits(x_min=self.xmin, x_max=self.xmax, y_min=self.ymin, y_max=self.ymax)
            self.ps.set_ticks(x_tick=self.x_ticks, x_num=self.xnum, y_tick=self.y_ticks, y_num=self.ynum)
            self.ps.specify_comps(*(sys.z.val for sys in self.parent.fit.sys))
            self.ps.specify_styles(lw=1.0, lw_total=self.fit_lw)
            if len(self.parent.fit.sys) > 0:
                self.ps.z_ref = self.parent.fit.sys[self.sys_ind-1].z.val
            else:
                self.ps.z_ref = self.parent.z_abs
            for i, p in enumerate(self.ps):
                p.name = ' '.join(self.parent.lines[self.ps.index(p)].split()[:2])
                if len(self.parent.lines[self.ps.index(p)].split()) > 2:
                    ind = int(self.parent.lines[self.ps.index(p)].split()[2][4:])
                else:
                    ind = self.parent.s.ind
                print(p.name, ind)
                s = self.parent.s[ind]
                if s.fit.n() > 0:
                    fit = np.array([s.fit.x(), s.fit.y()])
                    if self.show_comps:
                        fit_comp = []
                        for c in s.fit_comp:
                            fit_comp.append(np.array([c.x(), c.y()]))
                    else:
                        fit_comp = None
                else:
                    fit = None
                    fit_comp = None
                p.loaddata(d=np.array([s.spec.x(), s.spec.y(), s.spec.err(), s.mask.x()]), f=fit, fit_comp=fit_comp)
                if len(self.parent.lines[self.ps.index(p)].split()) == 4:
                    p.y_min, p.y_max = (float(l) for l in self.parent.lines[self.ps.index(p)].split()[2:])
                for l in self.parent.abs.lines:
                    if p.name == str(l.line):
                        p.wavelength = l.line.l()
                print(p.wavelength)
                p.show_comps = self.show_comps
                if any([s in p.name for s in ['H2', 'HD', 'CO']]):
                    p.name = ' '.join([p.name.split()[0][:-2], p.name.split()[1]])
                p.name_pos = [self.name_x_pos, self.name_y_pos]
                p.add_residual, p.sig = self.residuals, self.res_sigma
                p.y_formatter = self.y_formatter
                ax = p.plot_line()
                if self.show_cf and self.parent.fit.cf_fit:
                    for i in range(self.parent.fit.cf_num):
                        attr = 'cf_' + str(i)
                        if hasattr(self.parent.fit, attr):
                            cf = getattr(self.parent.fit, attr)
                            if (len(cf.addinfo.split('_'))>1 and cf.addinfo.split('_')[1]=='all') or (cf.addinfo.find('exp') > -1 and int(cf.addinfo[cf.addinfo.find('exp')+3:]) == ind):
                                ax.plot([np.max([(cf.min / p.wavelength / (1 + self.ps.z_ref) - 1) * 299794.26, p.x_min]), np.min([(cf.max / p.wavelength / (1 + self.ps.z_ref) - 1) * 299794.26, p.x_max])], [cf.val, cf.val], '--', color='orangered')

        else:
            self.ps = plot_spec(len(self.parent.plot.regions), font=self.font, font_labels=self.font_labels,
                           vel_scale=True, gray_out=self.gray_out, figure=fig)
            rects = rect_param(n_rows=int(self.rows), n_cols=int(self.cols), order=self.order,
                               v_indent=self.v_indent, h_indent=self.h_indent,
                               col_offset=self.col_offset, row_offset=self.row_offset)
            self.ps.specify_rects(rects)
            self.ps.set_ticklabels(xlabel=self.xlabel if self.xlabel.strip() != '' else None,  ylabel=self.ylabel if self.ylabel.strip() != '' else None)
            self.ps.set_limits(x_min=self.xmin, x_max=self.xmax, y_min=self.ymin, y_max=self.ymax)
            self.ps.set_ticks(x_tick=self.x_ticks, x_num=self.xnum, y_tick=self.y_ticks, y_num=self.ynum)
            self.ps.specify_comps(*(sys.z.val for sys in self.parent.fit.sys))
            self.ps.specify_styles(lw=1.0, lw_total=self.fit_lw)
            if len(self.parent.fit.sys) > 0:
                self.ps.z_ref = self.parent.fit.sys[self.sys_ind-1].z.val
            else:
                self.ps.z_ref = self.parent.z_abs
            for i, p in enumerate(self.ps):
                regions = self.lines.toPlainText().splitlines()
                #regions = self.parent.plot.regions
                st = str(regions[i]).split()
                print(st)
                p.x_min, p.x_max = (float(s) for s in st[0].split('..'))
                #p.y_formater = '%.1f'
                for s in st[1:]:
                    if 'name' in s:
                        p.name = s[5:]
                    if 'exp' in s:
                        ind = int(s[4:])
                if not any(['name' in s for s in st]):
                    p.name == ''
                if not any(['exp' in s for s in st]):
                    ind = self.parent.s.ind
                print(ind)
                s = self.parent.s[ind]
                if s.fit.n() > 0:
                    fit = np.array([s.fit.x(), s.fit.y()])
                    if self.show_comps:
                        fit_comp = []
                        for c in s.fit_comp:
                            fit_comp.append(np.array([c.x(), c.y()]))
                    else:
                        fit_comp = None
                else:
                    fit = None
                    fit_comp = None

                p.loaddata(d=np.array([s.spec.x(), s.spec.y(), s.spec.err(), s.mask.x()]), f=fit, fit_comp=fit_comp)
                #p.name = self.parent.regions[ps.index(p)]
                p.show_comps = self.show_comps
                p.name_pos = [self.name_x_pos, self.name_y_pos]
                p.add_residual, p.sig = self.residuals, self.res_sigma
                p.y_formatter = self.y_formatter
                ax = p.plot_line()
                if self.show_cf and self.parent.fit.cf_fit:
                    for i in range(self.parent.fit.cf_num):
                        attr = 'cf_' + str(i)
                        if hasattr(self.parent.fit, attr):
                            cf = getattr(self.parent.fit, attr)
                            if (len(cf.addinfo.split('_'))>1 and cf.addinfo.split('_')[1]=='all') or (cf.addinfo.find('exp') > -1 and int(cf.addinfo[cf.addinfo.find('exp')+3:]) == ind):
                                ax.plot([np.max([cf.min, p.x_min]), np.min([cf.max, p.x_max])], [cf.val, cf.val], '--', color='orangered')

                if self.show_H2.strip() != '':
                    p.showH2(ax, levels=[int(s) for s in self.show_H2.split()], pos=self.pos_H2)
                if self.show_cont:
                    print(self.show_cont)
                    ax.plot(s.cheb.x(), s.cheb.y(), '--k', lw=1)
                    if 0:
                        self.showContCorr(ax=ax)

        if savefig:
            plotfile = self.plotfile
        else:
            plotfile = os.path.dirname(os.path.realpath(__file__)) + '/output/lines.pdf'

        fig.savefig(plotfile, dpi=fig.dpi)
        plt.close(fig)

        if sys.platform.startswith('darwin'):
            subprocess.call(('open', plotfile))
        elif os.name == 'nt':
            os.startfile(plotfile)
        elif os.name == 'posix':
            subprocess.call(('xdg-open', plotfile))

    def saveSettings(self):
        fname = QFileDialog.getSaveFileName(self, 'Save settings...', self.parent.plot_set_folder)[0]
        self.parent.options('plot_set_folder', os.path.dirname(fname))

        if fname:
            f = open(fname, "wb")
            o = deepcopy(self.opts)
            for opt, func in self.opts.items():
                o[opt] = func(getattr(self, opt))
            pickle.dump(o, f)
            pickle.dump(str(self.parent.lines), f)
            #if self.regions:
            #    pickle.dump(self.lines.toPlainText(), f)
            #else:
            pickle.dump(str(self.parent.plot.regions), f)
            f.close()

    def showContCorr(self, ax):
        for i in range(5,15):
            print(i)
            self.parent.fitPoly(i)
            ax.plot(self.parent.s[self.parent.s.ind].cheb.x(), self.parent.s[self.parent.s.ind].cheb.y(), '-', lw=0.5, color='mediumseagreen')

    def loadSettings(self, fname=None):
        if fname is None:
            fname = QFileDialog.getOpenFileName(self, 'Load settings...', self.parent.plot_set_folder)[0]
            self.parent.options('plot_set_folder', os.path.dirname(fname))
        if fname:
            f = open(fname, "rb")
            o = pickle.load(f)
            for opt, item in o.items():
                setattr(self, opt, item)
            self.parent.lines.fromText(str(pickle.load(f)))
            self.parent.plot.regions.fromText(str(pickle.load(f)), sort=False)
            f.close()
        self.close()
        self.parent.showLines()

    def keyPressEvent(self, event):
        super(showLinesWidget, self).keyPressEvent(event)
        key = event.key()

        if not event.isAutoRepeat():
            if event.key() == Qt.Key_L:
                if (QApplication.keyboardModifiers() == Qt.ControlModifier):
                    self.parent.showlines.close()

    def closeEvent(self, ev):
        for opt, func in self.opts.items():
            print(opt, func(getattr(self, opt)))
            self.parent.options(opt, func(getattr(self, opt)))
        ev.accept()

class snapShotWidget(QWidget):

    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.resize(800, 250)
        self.move(200,100)

        self.initData()

        layout = QVBoxLayout()
        l = QHBoxLayout()

        self.filename = QLineEdit(self.parent.work_folder + '/figure.pdf')
        self.filename.setFixedSize(650, 30)
        self.getfilename = QPushButton('Choose')
        self.getfilename.setFixedSize(70, 30)
        self.getfilename.clicked[bool].connect(self.loadfile)
        self.setStyleSheet(open('config/styles.ini').read())
        l.addWidget(self.filename)
        l.addWidget(self.getfilename)
        l.addStretch(0)
        layout.addLayout(l)

        grid = QGridLayout()
        l = QHBoxLayout()
        l.addLayout(grid)
        l.addStretch(1)
        layout.addLayout(l)
        validator = QDoubleValidator()
        locale = QLocale('C')
        validator.setLocale(locale)
        # validator.ScientificNotation
        names = ['Size:', 'width:', '', 'height:', '',
                 'Fonts:', 'axis:', '', '', '',
                 'Label:', 'x:', '', 'y:', '',
                 'X-ticks:', 'scale:', '', 'num', '',
                 'Y-ticks:', 'scale:', '', 'num', '',
                 ]
        positions = [(i, j) for i in range(3) for j in range(5)]

        for position, name in zip(positions, names):
            if name == '':
                continue
            grid.addWidget(QLabel(name), *position)

        self.opt_but = OrderedDict([('snap_width', [0, 2]), ('snap_height', [0, 4]), ('snap_font', [1, 2]),
                                    ('snap_xlabel', [2, 2]), ('snap_ylabel', [2, 4]),
                                    ('snap_x_ticks', [3, 2]), ('snap_xnum', [3, 4]),
                                    ('snap_y_ticks', [4, 2]), ('snap_ynum', [4, 4])
                                     ])
        for opt, v in self.opt_but.items():
            b = QLineEdit(str(getattr(self, opt)))
            b.setFixedSize(100, 30)
            b.setValidator(validator)
            b.textChanged[str].connect(partial(self.onChanged, attr=opt))
            grid.addWidget(b, v[0], v[1])

        l = QHBoxLayout()
        self.ok = QPushButton('Plot')
        self.ok.setFixedSize(60, 30)
        self.ok.clicked[bool].connect(self.plot)

        self.cancel = QPushButton('Cancel')
        self.cancel.setFixedSize(60, 30)
        self.cancel.clicked[bool].connect(self.close)

        l.addStretch(0)
        l.addWidget(self.ok)
        l.addWidget(self.cancel)
        layout.addStretch(0)
        layout.addLayout(l)

        self.setLayout(layout)
        self.show()

    def initData(self):
        self.opts = {'snap_width': float, 'snap_height': float, 'snap_font': int,
                     'snap_xlabel': str, 'snap_ylabel': str,
                     'snap_x_ticks': float, 'snap_xnum': int, 'snap_y_ticks': float, 'snap_ynum': int
                     }
        for opt, func in self.opts.items():
            # print(opt, self.parent.options(opt), func(self.parent.options(opt)))
            setattr(self, opt, func(self.parent.options(opt)))

    def onChanged(self, text, attr=None):
        if attr is not None:
            setattr(self, attr, self.opts[attr](text))

    def loadfile(self):
        fname = QFileDialog.getSaveFileName(self, 'Export graph', self.parent.work_folder)
        self.filename.setText(fname[0])

    def plot(self):

        x_range = self.parent.plot.vb.viewRange()[0]
        y_range = self.parent.plot.vb.viewRange()[1]
        s = self.parent.s[0].spec
        fit = self.parent.s[0].fit
        mask = np.logical_and(s.x() > x_range[0], s.x() < x_range[1])

        fig, ax = plt.subplots(figsize=(self.snap_width,self.snap_height))
        font = 16

        if 0:
            ax.errorbar(s.x()[mask], s.y()[mask], s.err()[mask], lw=1, elinewidth=0.5, drawstyle='steps-mid',
                        color='k', ecolor='0.3', capsize=1.5)
        else:
            ax.errorbar(s.x()[mask], s.y()[mask], lw=1, elinewidth=0.5, drawstyle='steps-mid',
                        color='k', ecolor='0.3', capsize=1.5)

        if fit.n() > 0:
            ax.plot(fit.x()[mask], fit.y()[mask], lw=1, color='#e74c3c')

        ax.axis([x_range[0], x_range[1], y_range[0], y_range[1]])

        # >>> specify ticks:
        ax.xaxis.set_minor_locator(AutoMinorLocator(self.snap_xnum))
        ax.xaxis.set_major_locator(MultipleLocator(self.snap_x_ticks))
        ax.yaxis.set_minor_locator(AutoMinorLocator(self.snap_ynum))
        ax.yaxis.set_major_locator(MultipleLocator(self.snap_y_ticks))

        ax.tick_params(which='both', width=1)
        ax.tick_params(which='major', length=5)
        ax.tick_params(which='minor', length=3)
        ax.tick_params(axis='both', which='major', labelsize=self.snap_font-2)

        # >>> set axis ticks formater:
        #y_formater = "%.1f"
        #if y_formater is not None:
        #    ax.yaxis.set_major_formatter(FormatStrFormatter(y_formater))
        #x_formater = None
        #if x_formater is not None:
        #    ax.xaxis.set_major_formatter(FormatStrFormatter(.x_formater))

        # >>> set axis labels:
        ax.set_ylabel(self.snap_ylabel, fontsize=self.snap_font)
        ax.set_xlabel(self.snap_xlabel, fontsize=self.snap_font, labelpad=-4)

        print(self.filename.text())
        plt.savefig(self.filename.text())

    def closeEvent(self, ev):
        for opt, func in self.opts.items():
            self.parent.options(opt, func(getattr(self, opt)))
        ev.accept()

class fitMCMCWidget(QWidget):
    def __init__(self, parent):
        super(fitMCMCWidget, self).__init__()
        self.parent = parent

        self.initData()
        self.initGUI()
        self.setWindowTitle('Fit with MCMC')
        self.setStyleSheet(open('config/styles.ini').read())

    def initData(self):
        self.savedText = ''
        self.opts = OrderedDict([
            ('MCMC_walkers', int), ('MCMC_iters', int), ('MCMC_threads', int),
            ('MCMC_burnin', int), ('MCMC_smooth', bool), ('MCMC_truth', bool),
        ])
        for opt, func in self.opts.items():
            setattr(self, opt, func(self.parent.options(opt)))
        self.thread = None

    def initGUI(self):
        layout = QHBoxLayout()
        splitter = QSplitter(Qt.Horizontal)

        h = QHBoxLayout()
        grid = QGridLayout()
        validator = QDoubleValidator()
        locale = QLocale('C')
        validator.setLocale(locale)
        # validator.ScientificNotation
        names = ['Walkers:     ', '',
                 'Iterations:   ', '',
                 'Threads:', '',
                 'Priors:    ', '',
                 ]
        positions = [(i, j) for i in range(4) for j in range(2)]

        for position, name in zip(positions, names):
            if name == '':
                continue
            grid.addWidget(QLabel(name), *position)

        self.opt_but = OrderedDict([('MCMC_walkers', [0, 1]),
                                    ('MCMC_iters', [1, 1]),
                                    ('MCMC_threads', [2, 1]),
                                    ])
        for opt, v in self.opt_but.items():
            b = QLineEdit(str(getattr(self, opt)))
            b.setFixedSize(80, 30)
            b.setValidator(validator)
            b.textChanged[str].connect(partial(self.onChanged, attr=opt))
            grid.addWidget(b, v[0], v[1])
        self.priors = QTextEdit('')
        self.priors.setFixedSize(300, 400)
        self.priors.textChanged.connect(self.priorsChanged)
        self.priors.setText('# you can specify prior here \n# N_0_HI 19 0.2 0.3 \n# for comment use #')
        grid.addWidget(self.priors, 3, 1)

        self.chooseFit = chooseFitParsWidget(self.parent, closebutton=False)
        self.chooseFit.setFixedSize(200, 700)
        v = QVBoxLayout()
        v.addLayout(grid)
        v.addStretch(1)
        h.addLayout(v)
        h.addStretch(1)
        h.addWidget(self.chooseFit)

        self.start_button = QPushButton("Start")
        self.start_button.setCheckable(True)
        self.start_button.setFixedSize(120, 30)
        self.start_button.clicked[bool].connect(partial(self.start, True))
        self.continue_button = QPushButton("Continue")
        self.continue_button.setFixedSize(120, 30)
        self.continue_button.clicked[bool].connect(self.continueMC)
        self.stop_button = QPushButton("Stop")
        self.stop_button.setFixedSize(70, 30)
        self.stop_button.clicked[bool].connect(self.stop)
        hbox = QHBoxLayout()
        hbox.addWidget(self.start_button)
        hbox.addWidget(self.continue_button)
        hbox.addWidget(self.stop_button)
        hbox.addStretch(1)

        fitlayout = QVBoxLayout()
        #fitlayout.addWidget(QLabel('Fit MCMC:'))
        fitlayout.addLayout(h)
        fitlayout.addStretch(1)
        fitlayout.addLayout(hbox)
        widget = QWidget()
        widget.setLayout(fitlayout)
        splitter.addWidget(widget)

        h = QHBoxLayout()
        grid = QGridLayout()
        names = ['', '',
                 'Burn-in: ', '',
                 '', '',
                 '', '',
                 '', '',
                 'Results:', '',
                 ]
        positions = [(i, j) for i in range(6) for j in range(2)]

        for position, name in zip(positions, names):
            if name == '':
                continue
            grid.addWidget(QLabel(name), *position)

        self.opt_but = OrderedDict([('MCMC_burnin', [1, 1]),
                                    ])
        for opt, v in self.opt_but.items():
            b = QLineEdit(str(getattr(self, opt)))
            b.setFixedSize(80, 30)
            b.setValidator(validator)
            b.textChanged[str].connect(partial(self.onChanged, attr=opt))
            grid.addWidget(b, v[0], v[1])

        grid.addWidget(QLabel('Plot in:'), 0, 0)
        self.graph = QComboBox()
        self.graph.addItems(['chainConsumer', 'corner'])
        self.graph.setFixedSize(120, 30)
        self.graph.setCurrentIndex(['chainConsumer', 'corner'].index(self.parent.options('MCMC_graph')))
        self.graph.activated[str].connect(self.selectGraph)
        grid.addWidget(self.graph, 0, 1)
        self.smooth = QCheckBox('smooth')
        self.smooth.setChecked(bool(self.parent.options('MCMC_smooth')))
        self.smooth.clicked[bool].connect(partial(self.setOpts, 'smooth'))
        grid.addWidget(self.smooth, 2, 0)
        self.bestfit = QCheckBox('bestfit')
        self.bestfit.setChecked(bool(self.parent.options('MCMC_bestfit')))
        self.bestfit.clicked[bool].connect(partial(self.setOpts, 'bestfit'))
        grid.addWidget(self.bestfit, 3, 0)
        self.likelihood = QCheckBox('show likelihood')
        self.likelihood.setChecked(bool(self.parent.options('MCMC_likelihood')))
        self.likelihood.clicked[bool].connect(partial(self.setOpts, 'likelihood'))
        grid.addWidget(self.likelihood, 4, 0)
        self.results = QTextEdit('')
        self.results.setFixedSize(500, 400)
        self.results.setText('# fit results are here')
        self.results.textChanged.connect(self.fitresChanged)
        grid.addWidget(self.results, 5, 1)
        self.chooseShow = chooseShowParsWidget(self)
        self.chooseShow.setFixedSize(200, 700)
        v = QVBoxLayout()
        v.addLayout(grid)
        v.addStretch(1)
        h.addLayout(v)
        h.addStretch(1)
        h.addWidget(self.chooseShow)

        self.show_button = QPushButton("Show")
        self.show_button.setFixedSize(100, 30)
        self.show_button.clicked[bool].connect(self.showMC)
        self.stats_button = QPushButton("Stats")
        self.stats_button.setFixedSize(100, 30)
        self.stats_button.clicked[bool].connect(partial(self.stats, t='fit'))
        self.stats_all_button = QPushButton("Stats all")
        self.stats_all_button.setFixedSize(100, 30)
        self.stats_all_button.clicked[bool].connect(partial(self.stats, t='all'))
        self.stats_cols_button = QPushButton("Stats cols")
        self.stats_cols_button.setFixedSize(100, 30)
        self.stats_cols_button.clicked[bool].connect(partial(self.stats, t='cols'))
        self.check_button = QPushButton("Check")
        self.check_button.setFixedSize(100, 30)
        self.check_button.clicked[bool].connect(self.check)
        self.bestfit_button = QPushButton("Best fit")
        self.bestfit_button.setFixedSize(100, 30)
        self.bestfit_button.clicked[bool].connect(self.show_bestfit)

        self.loadres_button = QPushButton("Load")
        self.loadres_button.setFixedSize(120, 30)
        self.loadres_button.clicked[bool].connect(self.loadres)
        hbox = QHBoxLayout()
        hbox.addWidget(self.show_button)
        hbox.addWidget(self.stats_button)
        hbox.addWidget(self.stats_all_button)
        hbox.addWidget(self.stats_cols_button)
        hbox.addWidget(self.check_button)
        hbox.addWidget(self.bestfit_button)
        hbox.addStretch(1)
        hbox.addWidget(self.loadres_button)

        showlayout = QVBoxLayout()
        showlayout.addLayout(h)
        showlayout.addStretch(1)
        showlayout.addLayout(hbox)
        widget = QWidget()
        widget.setLayout(showlayout)
        splitter.addWidget(widget)
        splitter.setSizes([1000, 1200])
        layout.addWidget(splitter)

        self.setLayout(layout)

        self.setGeometry(200, 200, 1450, 800)
        self.setWindowTitle('Fit model')
        self.show()

    def onChanged(self, text, attr=None):
        if attr is not None:
            setattr(self, attr, self.opts[attr](text))
            self.parent.options(attr, self.opts[attr](text))

    def priorsChanged(self):
        self.prior = {}
        for line in self.priors.toPlainText().splitlines():
            if not line.startswith('#'):
                words = line.split()
                if words[0] in self.parent.fit.pars():
                    if len(words) == 3:
                        self.prior[words[0]] = a(float(words[1]), float(words[2]), 'd')
                    elif len(words) == 4:
                        self.prior[words[0]] = a(float(words[1]), float(words[2]), float(words[3]), 'd')

    def fitresChanged(self):
        for line in self.results.toPlainText().splitlines():
            if not line.startswith('#'):
                words = line.split()
                if words[0] in self.parent.fit.pars():
                    if len(words) == 3:
                        print(words[2])
                        self.parent.fit.setValue(words[0], words[2], attr='unc')

    def setOpts(self, arg=None):
        setattr(self, 'MCMC_'+arg, getattr(self, arg).isChecked())
        print(arg, getattr(self, arg).isChecked(), getattr(self, 'MCMC_'+arg))
        self.parent.options('MCMC_'+arg, getattr(self, 'MCMC_'+arg))

    def selectGraph(self, text):
        self.parent.options('MCMC_graph', text)
        self.graph.setCurrentIndex(['chainConsumer', 'corner'].index(self.parent.options('MCMC_graph')))

    def start(self, init=True):
        if self.thread is None:
            self.start_button.setChecked(True)
            if 0:
                from multiprocessing import Process
                self.thread = Process(target=dosome, args=(1,))
                #self.thread = Process(target=self.MCMC, args=(self,), kwargs={'init': init})
            else:
                self.thread = StoppableThread(target=self.MCMC, args=(), kwargs={'init': init}, daemon=True)
                print(self.thread.isDaemon())
                self.thread.daemon = True
                #self.thread = threading.Thread(target=self.MCMC, args=(), kwargs={'init': init}, daemon=True)
            self.thread.start()

    def stop(self):
        self.start_button.setChecked(False)
        if 1:
            self.thread.terminate()
        else:
            self.thread.stop()
        self.thread = None

    def continueMC(self):
        self.start(init=False)

    def MCMC(self, init=True):
        self.parent.setFit(comp=-1)
        nwalkers = int(self.parent.options('MCMC_walkers'))
        nsteps = int(self.parent.options('MCMC_iters'))
        threads = int(self.parent.options('MCMC_threads'))

        self.parent.s.prepareFit(-1, all=False)

        if init:
            pars, pos = [], []
            for par in self.parent.fit.list_fit():
                pars.append(str(par))
                pos.append(par.val * np.ones(nwalkers) + np.random.randn(nwalkers) * par.step)
            pos = np.array(pos).transpose()
        else:
            with open("output/current.pkl", "rb") as f:
                pars = pickle.load(f)
                pos = pickle.load(f)

        if pars == [str(p) for p in self.parent.fit.list_fit()]:
            ndim = len(pars)

            sampler = emcee.EnsembleSampler(nwalkers, ndim, lnprob, args=[pars, self.prior, self], threads=threads)

            samples = np.array([[self.parent.fit.getValue(p) for p in pars]])
            lnprobs = np.array([lnprob(samples[0], pars, self.prior, self)])

            for i, result in enumerate(sampler.sample(pos, iterations=nsteps, storechain=False)):
                print(i)
                self.parent.MCMCprogress.setText('     MCMC is running: {0:d} / {1:d}'.format(i, nsteps))
                samples = np.concatenate([samples, result[0]], axis=0)
                lnprobs = np.concatenate([lnprobs, result[1]])
                with open("output/chain.pkl", "wb") as f:
                    pickle.dump(pars, f)
                    pickle.dump(nwalkers, f)
                    pickle.dump(samples, f)
                    pickle.dump(lnprobs, f)
                with open("output/current.pkl", "wb") as f:
                    pickle.dump(pars, f)
                    pickle.dump(result[0], f)
            self.showMC()

            self.thread = None
            self.start_button.setChecked(False)

    def readChain(self, ):
        with open("output/chain.pkl", "rb") as f:
            return pickle.load(f), pickle.load(f), pickle.load(f), pickle.load(f)

    def showMC(self):
        pars, nwalkers, samples, lnprobs = self.readChain()

        mask = np.array([self.parent.fit.list()[[str(i) for i in self.parent.fit.list()].index(p)].show for p in pars])
        names = [str(p).replace('_', ' ') for p in self.parent.fit.list_fit() if p.show]
        if self.parent.options('MCMC_likelihood'):
            names = [r'$\chi^2$'] + pars
            samples = np.insert(samples, 0, lnprobs, axis=1)
            mask = np.insert(mask, 0, True)
        imax = np.argmin(lnprobs)
        truth = samples[imax][np.where(mask)[0]] if self.parent.options('MCMC_bestfit') else None
        print('best fit:', truth)
        burnin = int(self.parent.options('MCMC_burnin'))
        if nwalkers * burnin < samples.shape[0]:
            if self.parent.options('MCMC_graph') == 'chainConsumer':
                from chainconsumer import ChainConsumer
                c = ChainConsumer()
                c.add_chain(samples[nwalkers * burnin:, np.where(mask)[0]], walkers=nwalkers,
                            parameters=names)
                c.configure(smooth=self.parent.options('MCMC_smooth'),
                            cloud=True,
                            sigmas=[0, 1, 2, 3],
                            )
                c.configure_truth(ls='--', lw=1., c='lightblue')  # c='darkorange')

                fig = c.plotter.plot(figsize=(30, 30),
                                        #filename="output/fit.png",
                                        display=True,
                                        truth=truth
                                        )
            if self.parent.options('MCMC_graph') == 'corner':
                import corner
                figure = corner.corner(samples[nwalkers * burnin:, np.where(mask)[0]],
                                       labels=names,
                                       show_titles=True,
                                       plot_contours=self.parent.options('MCMC_smooth'),
                                       truths=truth,
                                       )
                plt.show()

    def stats(self, t='fit'):
        pars, nwalkers, samples, lnprobs = self.readChain()

        burnin = int(self.parent.options('MCMC_burnin'))

        truth = samples[np.argmin(lnprobs)] if bool(self.parent.options('MCMC_bestfit')) else None

        self.results.setText('')

        if t == 'fit':
            mask = np.array([p.show for p in self.parent.fit.list_fit()])
            names = [str(p) for p in self.parent.fit.list_fit() if p.show]

            k = int(np.sum(mask)) #samples.shape[1]
            n_hor = int(k ** 0.5)
            if n_hor <= 1:
                n_hor = 2
            n_vert = k // n_hor + 1 if k % n_hor > 0 else k // n_hor

            fig, ax = plt.subplots(nrows=n_vert, ncols=n_hor, figsize=(6 * n_vert, 4 * n_hor))
            k = 0
            for i, p in enumerate(pars):
                print(i, p)
                if p in names:
                    x = np.linspace(np.min(samples[nwalkers * burnin + 1:, i]), np.max(samples[nwalkers * burnin + 1:, i]), 50)
                    kde = gaussian_kde(samples[nwalkers * burnin + 1:, i])
                    d = distr1d(x, kde(x))
                    print(x, kde(x))
                    d.dopoint()
                    d.dointerval()
                    res = a(d.point, d.interval[1] - d.point, d.point - d.interval[0])
                    self.parent.fit.setValue(p, res, 'unc')
                    self.parent.fit.setValue(p, res.val)
                    print(res.plus, res.minus)
                    f = np.asarray([res.plus, res.minus])
                    f = int(np.round(np.abs(np.log10(np.min(f[np.nonzero(f)])))) + 1)
                    print(p, res.latex(f=f))
                    self.results.setText(self.results.toPlainText() + p + ': ' + res.latex(f=f) + '\n')
                    vert, hor = k // n_hor, k % n_hor
                    k += 1
                    d.plot(conf=0.683, ax=ax[vert, hor], ylabel='')
                    if truth is not None:
                        ax[vert, hor].axvline(truth[i], c='navy', ls='--', lw=1)
                    ax[vert, hor].yaxis.set_ticklabels([])
                    ax[vert, hor].yaxis.set_ticks([])
                    ax[vert, hor].text(.05, .9, str(p).replace('_', ' '), ha='left', va='top', transform=ax[vert, hor].transAxes)
                    ax[vert, hor].text(.95, .9, self.parent.fit.getPar(p).fitres(latex=True, showname=False), ha='right', va='top', transform=ax[vert, hor].transAxes)
                    #ax[vert, hor].set_title(pars[i].replace('_', ' '))

        else:
            values = []
            for k in range(nwalkers * burnin + 1, samples.shape[0]):
                for xi, p in zip(samples[k], pars):
                    self.parent.fit.setValue(p, xi)
                self.parent.fit.update()
                values.append([p.val for p in self.parent.fit.list()])

            values = np.asarray(values)
            print(t)

            if t == 'all':
                k = len(self.parent.fit.list())  # samples.shape[1]
                n_hor = int(k ** 0.5)
                if n_hor <= 1:
                    n_hor = 2
                n_vert = k // n_hor + 1 if k % n_hor > 0 else k // n_hor

                fig, ax = plt.subplots(nrows=n_vert, ncols=n_hor, figsize=(6 * n_vert, 4 * n_hor))

                k = 0
                for i, p in enumerate(self.parent.fit.list()):
                    if np.std(values[:, i]) > 0:
                        d = distr1d(values[:, i])
                        d.dopoint()
                        d.dointerval()
                        res = a(d.point, d.interval[1] - d.point, d.point - d.interval[0])
                        f = int(np.round(np.abs(np.log10(np.min([res.plus, res.minus])))) + 1)
                        self.results.setText(self.results.toPlainText() + str(p) + ': ' + res.latex(f=f) + '\n')
                        #vert, hor = int((i) / n_hor), i - n_hor * int((i) / n_hor)
                        vert, hor = k // n_hor, k % n_hor
                        k += 1
                        d.plot(conf=0.683, ax=ax[vert, hor], ylabel='')
                        ax[vert, hor].yaxis.set_ticklabels([])
                        ax[vert, hor].yaxis.set_ticks([])
                        ax[vert, hor].text(.1, .9, str(p).replace('_', ' '), ha='left', va='top', transform=ax[vert, hor].transAxes)
                        #ax[vert, hor].set_title(str(p).replace('_', ' '))

            elif t == 'cols':
                sp = list()
                for sys in self.parent.fit.sys:
                    for s in sys.sp.keys():
                        if s not in sp:
                            sp.append(s)
                    for el in ['H2', 'HD', 'CO', 'CI', 'CII']:
                        if any([el in s for s in sys.sp.keys()]):
                            sys.addSpecies(el, 'total')
                            self.parent.fit.total.addSpecies(el)
                for s in sp:
                    self.parent.fit.total.addSpecies(s)

                sp = self.parent.fit.list_total()
                n_hor = int(len(sp) ** 0.5)
                if n_hor <= 1:
                    n_hor = 2
                n_vert = len(sp) // n_hor + 1 if len(sp) % n_hor > 0 else len(sp) // n_hor


                fig, ax = plt.subplots(nrows=n_vert, ncols=n_hor, figsize=(6 * n_vert, 4 * n_hor))
                i = 0
                for k, v in sp.items():
                    print(k, v)
                    if 'total' in k:
                        inds = np.where([k.split('_')[2] in str(s) and str(s)[0] == 'N' for s in self.parent.fit.list()])[0]
                    else:
                        inds = np.where([k[2:] in str(s) and str(s)[0] == 'N' for s in self.parent.fit.list()])[0]
                    d = distr1d(np.log10(np.sum(10 ** values[:, inds], axis=1)))
                    d.dopoint()
                    d.dointerval()
                    res = a(d.point, d.interval[1] - d.point, d.point - d.interval[0])
                    v.set(res, attr='unc')
                    v.set(d.point)
                    f = int(np.round(np.abs(np.log10(np.min([res.plus, res.minus])))) + 1)
                    self.results.setText(self.results.toPlainText() + k + ': ' + v.fitres(latex=True, dec=f, showname=False) + '\n')
                    vert, hor = i // n_hor, i % n_hor
                    i += 1
                    d.plot(conf=0.683, ax=ax[vert, hor], ylabel='')
                    ax[vert, hor].yaxis.set_ticklabels([])
                    ax[vert, hor].yaxis.set_ticks([])
                    ax[vert, hor].text(.1, .9, k.replace('_', ' '), ha='left', va='top', transform=ax[vert, hor].transAxes)

        for i in range(i, n_hor * n_vert):
            vert, hor = i // n_hor, i % n_hor
            fig.delaxes(ax[vert, hor])

        plt.tight_layout()
        plt.subplots_adjust(wspace=0)
        plt.show()

    def check(self):
        self.MCMCqc()

    def MCMCqc(self, qc='all'):
        pars, nwalkers, samples, lnprobs = self.readChain()
        print(pars, lnprobs)

        if any([s in qc for s in ['current', 'moments', 'all']]):
            k = samples.shape[1]
            n_hor = int(k ** 0.5)
            if n_hor <= 1:
                n_hor = 2
            n_vert = int(k / n_hor + 1)

        if any([s in qc for s in ['current', 'all']]):
            for i, p in enumerate(pars):
                if p.startswith('z'):
                    samples[:, i] = samples[:, i] * 1000
            fig, ax0 = plt.subplots(nrows=n_vert, ncols=n_hor, figsize=(6 * n_vert, 4 * n_hor))
            ax0[0, 0].hist(-lnprobs[-nwalkers:], 20, density=1, histtype='bar', color='crimson', label='$\chi^2$')
            ax0[0, 0].legend()
            ax0[0, 0].set_title('$\chi^2$ distribution')
            for i in range(k):
                vert, hor = int((i + 1) / n_hor), i + 1 - n_hor * int((i + 1) / n_hor)
                ax0[vert, hor].scatter(samples[-nwalkers:, i], -lnprobs[-nwalkers:], c='r')
                ax0[vert, hor].text(.1, .9, str(pars[i]).replace('_', ' '), ha='left', va='top',
                                   transform=ax0[vert, hor].transAxes)

        plt.subplots_adjust(wspace=0)
        plt.tight_layout()

        if any([s in qc for s in ['moments', 'all']]):
            ind = np.random.randint(0,nwalkers)
            SomeChain = samples[1 + ind::nwalkers,:]
            SomeChain = samples[1 + ind::nwalkers,:]
            print((samples.shape[0])/nwalkers)
            niters = int((samples.shape[0])/nwalkers)
            mean, std, chimin = np.empty([len(pars), niters]), np.empty([len(pars), niters]), np.empty([3, niters])
            for i in range(niters):
                mean[:, i] = np.mean(samples[i*nwalkers+1:(i+1)*nwalkers+1, :], axis=0)
                std[:, i] = np.std(samples[i*nwalkers+1:(i+1)*nwalkers+1, :], axis=0)
                chimin[0, i] = np.min(-lnprobs[i*nwalkers+1:(i+1)*nwalkers+1])
                chimin[1, i] = np.mean(-lnprobs[i * nwalkers + 1:(i + 1) * nwalkers + 1])
                chimin[2, i] = np.std(-lnprobs[i * nwalkers + 1:(i + 1) * nwalkers + 1])
            fig, ax = plt.subplots(nrows=n_vert, ncols=n_hor, figsize=(6 * n_vert, 4 * n_hor), sharex=True)
            ax[0, 0].plot(np.arange(niters), np.log10(chimin[0]), label='$\chi^2_{min}$')
            ax[0, 0].plot(np.arange(niters), np.log10(-lnprobs[ind::nwalkers]), label='$\chi^2$ at chain')
            ax[0, 0].plot(np.arange(niters), np.log10(chimin[1]), label='$\chi^2$ mean')
            ax[0, 0].plot(np.arange(niters), np.log10(chimin[2]), label='$\chi^2$ disp')
            ax[0, 0].legend(loc=1)
            for i in range(k):
                vert, hor = int((i + 1) / n_hor), i + 1 - n_hor * int((i + 1) / n_hor)
                # print(vert, hor)
                ax[vert, hor].plot(np.arange(niters), mean[i], color='r')
                ax[vert, hor].fill_between(np.arange(niters), mean[i]-std[i], mean[i]+std[i],
                                           facecolor='green', interpolate=True, alpha=0.5)
                ax[vert, hor].plot(np.arange(niters), SomeChain[:, i], color='b')
                ax[vert, hor].text(.1, .9, str(pars[i]).replace('_', ' '), ha='left', va='top', transform=ax[vert, hor].transAxes)
                #ax[vert, hor].set_title(pars[i].replace('_', ' '))

        plt.tight_layout()
        plt.subplots_adjust(hspace=0)
        plt.show()

    def show_bestfit(self):
        pars, nwalkers, samples, lnprobs = self.readChain()
        truth = samples[np.argmin(lnprobs)]
        for p, t in zip(pars, truth):
            print(p, t)
            self.parent.fit.setValue(p, t)

    def loadres(self):
        fname = QFileDialog.getOpenFileName(self, 'Load MCMC results', self.parent.work_folder)

        if fname[0]:
            self.parent.options('work_folder', os.path.dirname(fname[0]))
            if fname[0].endswith('.dat'):
                with open(fname[0]) as f:
                    nwalkers = int(f.readline())
                    pars = f.readline().split()
                    for i, par in enumerate(pars):
                        p = par.split('_')
                        if len(p) > 1:
                            p[1] = str(int(p[1])-1)
                        pars[i] = '_'.join(p)
                    print(pars)
                samples = np.genfromtxt(fname[0], skip_header=2)

            with open("output/chain.pkl", "wb") as f:
                pickle.dump(pars[1:-1], f)
                pickle.dump(nwalkers, f)
                pickle.dump(samples[:, 1:-1], f)
                pickle.dump(samples[:, 0], f)

    def keyPressEvent(self, event):
        super(fitMCMCWidget, self).keyPressEvent(event)
        key = event.key()

        if not event.isAutoRepeat():
            if event.key() == Qt.Key_M:
                if (QApplication.keyboardModifiers() == Qt.ControlModifier):
                    self.parent.MCMC.close()

    def closeEvent(self, event):
        #for opt, func in self.opts.items():
        #    print(opt, func(getattr(self, opt)))
        #    self.parent.options(opt, func(getattr(self, opt)))
        self.parent.MCMC = None

class fitExtWidget(QWidget):
    def __init__(self, parent):
        super(fitExtWidget, self).__init__()
        self.parent = parent
        self.setStyleSheet(open('config/styles.ini').read())
        self.initUI()

    def initUI(self):
        l = QGridLayout()

        self.z_em = QCheckBox('z_em:', self)
        self.z_em.setChecked(False)
        l.addWidget(self.z_em, 0, 0)
        self.z_em_value = QLineEdit(self)
        self.z_em_value.setText('3.04')
        l.addWidget(self.z_em_value, 0, 1)

        self.z_abs = QCheckBox('z_abs:', self)
        self.z_abs.setChecked(False)
        l.addWidget(self.z_abs, 1, 0)
        self.z_abs_value = QLineEdit(self)
        self.z_abs_value.setText(str(self.parent.z_abs))
        l.addWidget(self.z_abs_value, 1, 1)

        self.Av = QCheckBox('Av:', self)
        self.Av.setChecked(False)
        l.addWidget(self.Av, 2, 0)
        self.Av_value = QLineEdit(self)
        self.Av_value.setText('0.0')
        l.addWidget(self.Av_value, 2, 1)

        self.Av_bump = QCheckBox('Av_bump:', self)
        self.Av_bump.setChecked(False)
        l.addWidget(self.Av_bump, 3, 0)
        self.Av_bump_value = QLineEdit(self)
        self.Av_bump_value.setText('0.0')
        l.addWidget(self.Av_bump_value, 3, 1)

        self.fit = QPushButton('Fit', self)
        self.fit.setFixedSize(100, 30)
        self.fit.clicked.connect(self.fitExt)
        l.addWidget(self.fit, 4, 0)

        self.setLayout(l)
        self.setGeometry(300, 300, 280, 230)
        self.setWindowTitle('fit Extinction curve')
        self.show()

    def fitExt(self, signal, template='HST'):

        z_em = float(self.z_em_value.text())
        z_abs = float(self.z_abs_value.text())
        Av = float(self.Av_value.text())
        Av_bump = float(self.Av_bump_value.text())
        if template in ['VanDenBerk', 'HST', 'const']:
            if template == 'VanDenBerk':
                data = np.genfromtxt('data/SDSS/medianQSO.dat', skip_header=2, unpack=True)
                data[0] *= (1 + z_em)
                fill_value = (1.3, 0.5)
            elif template == 'HST':
                data = np.genfromtxt('data/SDSS/hst_composite.dat', skip_header=2, unpack=True)
                data[0] *= (1 + z_em)
                fill_value = 'extrapolate'
                print('HST_data', data)
            elif template == 'const':
                data = np.ones((2, 10))
                data[0] = np.linspace(xmin, xmax, 10)
            inter = interp1d(data[0], data[1], bounds_error=False, fill_value=fill_value, assume_sorted=True)
        s = self.parent.s[self.parent.s.ind]

        y = inter(s.spec.raw.x[:])
        if Av > 0 or Av_bump > 0:
            y *= add_ext_bump(x=s.spec.raw.x, z_ext=z_abs, Av=Av, Av_bump=Av_bump)

        mask = np.logical_and(s.spec.raw.x > 1465 * (1 + z_em), s.spec.raw.x < 1475 * (1 + z_em))
        print(np.sum(s.spec.raw.y[mask]), np.sum(y[mask]))
        y *= np.sum(s.spec.raw.y[mask]) / np.sum(y[mask])
        s.cont.x, s.cont.y = s.spec.raw.x[:], y
        s.cont.n = len(s.cont.y)
        s.cont_mask = np.logical_not(np.isnan(s.spec.raw.x))
        s.redraw()

    def keyPressEvent(self, qKeyEvent):
        if qKeyEvent.key() == Qt.Key_Return:
            self.fitExt()

class extract2dWidget(QWidget):
    def __init__(self, parent):
        super(extract2dWidget, self).__init__()
        self.parent = parent
        self.mask_type = 'moffat'
        self.trace_pos = None
        self.trace_width = [None, None]
        self.init_GUI()
        self.init_Parameters()
        self.setStyleSheet(open('config/styles.ini').read())
        self.setGeometry(200, 200, 550, 800)
        self.setWindowTitle('Spectrum Extraction')

    def init_Parameters(self):
        self.opts = OrderedDict([
            ('trace_step', ['traceStep', int, 200]),
            ('exp_pixel', ['expPixel', int, 1]),
            ('exp_factor', ['expFactor', float, 3]),
            ('extr_height', ['extrHeight', float, 1]),
            ('extr_width', ['extrWidth', float, 3]),
            ('extr_slit', ['extrSlit', float, 0.9]),
            ('extr_window', ['extrWindow', int, 0]),
            ('extr_border', ['extrBorder', int, 1]),
            ('extr_conf', ['extrConf', float, 0.03]),
            ('sky_poly', ['skyPoly', int, 3]),
            ('sky_smooth', ['skySmooth', int, 0]),
            ('sky_smooth_coef', ['skySmoothCoef', float, 0.3]),
            ('helio_corr', ['helioCorr', float, 20.682]),
            ('rescale_window', ['rescaleWindow', int, 30]),
        ])
        for opt in self.opts.keys():
            setattr(self, opt, self.opts[opt][1](self.opts[opt][2]))
            getattr(self, self.opts[opt][0]).setText(str(getattr(self, opt)))

    def init_GUI(self):
        layout = QVBoxLayout()

        self.tab = QTabWidget()
        self.tab.setGeometry(0, 0, 550, 550)
        self.tab.setMinimumSize(550, 550)
        self.tab.setCurrentIndex(0)
        self.init_GUI_CosmicRays()
        self.init_GUI_Extraction()
        self.init_GUI_Sky()
        self.init_GUI_Correction()
        layout.addWidget(self.tab)
        hl = QHBoxLayout()
        exposure = QPushButton('Exposure:')
        exposure.setFixedSize(100, 30)
        exposure.clicked.connect(self.changeExp)
        self.expchoose = QComboBox()
        self.expchoose.setFixedSize(400, 30)
        for s in self.parent.s:
            self.expchoose.addItem(s.filename)
        if len(self.parent.s) > 0:
            self.exp_ind = self.parent.s.ind
            self.expchoose.currentIndexChanged.connect(self.onExpChoose)
            self.expchoose.setCurrentIndex(self.exp_ind)
        hl.addWidget(exposure)
        hl.addWidget(self.expchoose)
        hl.addStretch(0)
        layout.addLayout(hl)
        layout.addStretch(1)
        self.setLayout(layout)

    def init_GUI_CosmicRays(self):

        frame = QFrame(self)
        layout = QVBoxLayout()
        self.input = QTextEdit()
        self.input.setText('sigclip=4.5\nsigfrac=0.3\nobjlim=5.\npssl=0.0\ngain=1.0\nreadnoise=6.5\nsatlevel=65535.0\nniter=4\nsepmed=1\ncleantype=meanmask\nfsmode=median\npsffwhm=2.5\npsfsize=7\npsfk=None\npsfbeta=4.765')
        layout.addWidget(QLabel('cosmicray_lacosmic arguments:'))
        layout.addWidget(self.input)
        hl = QHBoxLayout()
        run = QPushButton('Run')
        run.setFixedSize(80, 30)
        run.clicked.connect(partial(self.cr, update='new'))
        add = QPushButton('Add')
        add.setFixedSize(80, 30)
        add.clicked.connect(partial(self.cr, update='add'))
        raw = QPushButton('From raw')
        raw.setFixedSize(80, 30)
        raw.clicked.connect(partial(self.cr, update='raw'))
        clear = QPushButton('Clear')
        clear.setFixedSize(100, 30)
        clear.clicked.connect(self.clear)
        hl.addWidget(run)
        hl.addWidget(add)
        hl.addWidget(raw)
        hl.addStretch(0)
        hl.addWidget(clear)
        layout.addLayout(hl)

        hl = QHBoxLayout()
        fromexp = QPushButton('From exposure:')
        fromexp.setFixedSize(120, 30)
        fromexp.clicked.connect(partial(self.crfromexp))
        hl.addWidget(fromexp)
        self.expCrChoose = QComboBox()
        self.expCrChoose.setFixedSize(250, 30)
        for s in self.parent.s:
            self.expCrChoose.addItem(s.filename)
        if len(self.parent.s) > 0:
            self.exp_cr_ind = self.parent.s.ind
            self.expCrChoose.setCurrentIndex(self.exp_cr_ind)
        self.expCrChoose.currentIndexChanged.connect(partial(self.onExpChoose, name='exp_cr_ind'))
        hl.addWidget(fromexp)
        hl.addWidget(self.expCrChoose)
        hl.addStretch(0)
        layout.addLayout(hl)

        hl = QHBoxLayout()
        expand = QPushButton('Expand:')
        expand.setFixedSize(120, 30)
        expand.clicked.connect(self.expand)
        self.expPixel = QLineEdit()
        self.expPixel.setFixedSize(40, 30)
        self.expPixel.textChanged.connect(partial(self.edited, 'exp_pixel'))
        self.expFactor = QLineEdit()
        self.expFactor.setFixedSize(40, 30)
        self.expFactor.textChanged.connect(partial(self.edited, 'exp_factor'))
        intelExpand = QPushButton('Intel. expand')
        intelExpand.setFixedSize(120, 30)
        intelExpand.clicked.connect(self.intelExpand)
        hl.addWidget(expand)
        hl.addWidget(self.expPixel)
        hl.addStretch(0)
        hl.addWidget(self.expFactor)
        hl.addWidget(intelExpand)
        layout.addLayout(hl)
        hl = QHBoxLayout()
        clean = QPushButton('Clean')
        clean.setFixedSize(120, 30)
        clean.clicked.connect(self.clean)
        hl.addWidget(clean)
        hl.addStretch(0)
        layout.addLayout(hl)
        hl = QHBoxLayout()
        extrapolate = QPushButton('Extrapolate')
        extrapolate.setFixedSize(120, 30)
        extrapolate.clicked.connect(partial(self.extrapolate, inplace=False))
        self.extrHeight = QLineEdit()
        self.extrHeight.setFixedSize(40, 30)
        self.extrHeight.textChanged.connect(partial(self.edited, 'extr_height'))
        self.extrWidth = QLineEdit()
        self.extrWidth.setFixedSize(40, 30)
        self.extrWidth.textChanged.connect(partial(self.edited, 'extr_width'))
        hl.addWidget(extrapolate)
        hl.addWidget(QLabel('h:'))
        hl.addWidget(self.extrHeight)
        hl.addWidget(QLabel('w:'))
        hl.addWidget(self.extrWidth)
        hl.addStretch(0)
        layout.addLayout(hl)
        frame.setLayout(layout)
        self.tab.addTab(frame, 'Cosmic Rays')

    def init_GUI_Extraction(self):

        frame = QFrame(self)
        layout = QVBoxLayout()

        hl = QHBoxLayout()
        trace = QPushButton('Trace each:')
        trace.setFixedSize(120, 30)
        trace.clicked.connect(partial(self.trace))
        self.traceStep = QLineEdit()
        self.traceStep.setFixedSize(50, 30)
        self.traceStep.textChanged.connect(partial(self.edited, 'trace_step'))
        hl.addWidget(trace)
        hl.addWidget(self.traceStep)
        hl.addStretch(0)
        layout.addLayout(hl)

        hl = QHBoxLayout()
        traceFit = QPushButton('Fit trace')
        traceFit.setFixedSize(120, 30)
        traceFit.clicked.connect(partial(self.trace_fit))
        traceStat = QPushButton('Trace stats')
        traceStat.setFixedSize(120, 30)
        traceStat.clicked.connect(partial(self.trace_stat))
        hl.addWidget(traceFit)
        hl.addWidget(traceStat)
        hl.addStretch(0)
        layout.addLayout(hl)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("QFrame {border: 0.5px solid rgb(100,100,100);}")
        layout.addWidget(line)

        hl = QHBoxLayout()
        hl.addWidget(QLabel('Slit:'))
        self.extrSlit = QLineEdit()
        self.extrSlit.setFixedSize(40, 30)
        self.extrSlit.textChanged.connect(partial(self.edited, 'extr_slit'))
        hl.addWidget(self.extrSlit)
        hl.addStretch(0)
        layout.addLayout(hl)

        hl = QHBoxLayout()
        self.helio = QCheckBox('Helio. corr:')
        self.helio.setFixedSize(80, 30)
        self.helio.setChecked(True)
        hl.addWidget(self.helio)
        self.helioCorr = QLineEdit()
        self.helioCorr.setFixedSize(60, 30)
        self.helioCorr.textChanged.connect(partial(self.edited, 'helio_corr'))
        hl.addWidget(self.helioCorr)
        hl.addStretch(0)
        layout.addLayout(hl)

        hl = QHBoxLayout()
        self.airVac = QCheckBox('Airvac. corr.')
        self.airVac.setFixedSize(80, 30)
        self.airVac.setChecked(True)
        hl.addWidget(self.airVac)
        hl.addStretch(0)
        layout.addLayout(hl)

        hl = QHBoxLayout()
        extract = QPushButton('Extract')
        extract.setFixedSize(120, 30)
        extract.clicked.connect(partial(self.extract))
        hl.addWidget(extract)
        hl.addStretch(0)
        layout.addLayout(hl)
        layout.addStretch(0)
        frame.setLayout(layout)
        self.tab.addTab(frame, 'Extract')

    def init_GUI_Sky(self):

        frame = QFrame(self)
        layout = QVBoxLayout()

        hl = QHBoxLayout()
        hl.addWidget(QLabel('Window:'))
        self.extrWindow = QLineEdit()
        self.extrWindow.setFixedSize(40, 30)
        self.extrWindow.textChanged.connect(partial(self.edited, 'extr_window'))
        hl.addWidget(self.extrWindow)
        hl.addStretch(0)
        layout.addLayout(hl)

        hl = QHBoxLayout()
        hl.addWidget(QLabel('Border indent:'))
        self.extrBorder = QLineEdit()
        self.extrBorder.setFixedSize(60, 30)
        self.extrBorder.textChanged.connect(partial(self.edited, 'extr_border'))
        hl.addWidget(self.extrBorder)
        hl.addStretch(0)
        layout.addLayout(hl)

        hl = QHBoxLayout()
        hl.addWidget(QLabel('Profile confidence:'))
        self.extrConf = QLineEdit()
        self.extrConf.setFixedSize(60, 30)
        self.extrConf.textChanged.connect(partial(self.edited, 'extr_conf'))
        hl.addWidget(self.extrConf)
        hl.addStretch(0)
        layout.addLayout(hl)

        hl = QHBoxLayout()
        hl.addWidget(QLabel('Model:'))
        self.skymodel = QComboBox()
        self.skymodel.setFixedSize(80, 30)
        self.skymodel.addItems(['median', 'polynomial', 'robust', 'wavy'])
        self.skymodeltype = 'wavy'
        self.skymodel.setCurrentText(self.skymodeltype)
        self.skymodel.activated[str].connect(self.skyModel)
        hl.addWidget(self.skymodel)
        hl.addStretch(0)
        layout.addLayout(hl)

        hl = QHBoxLayout()
        hl.addWidget(QLabel('Poly order:'))
        self.skyPoly = QLineEdit()
        self.skyPoly.setFixedSize(60, 30)
        self.skyPoly.textChanged.connect(partial(self.edited, 'sky_poly'))
        hl.addWidget(self.skyPoly)
        hl.addStretch(0)
        layout.addLayout(hl)

        hl = QHBoxLayout()
        hl.addWidget(QLabel('Smooth:'))
        self.skySmooth = QLineEdit()
        self.skySmooth.setFixedSize(60, 30)
        self.skySmooth.textChanged.connect(partial(self.edited, 'sky_smooth'))
        hl.addWidget(self.skySmooth)
        hl.addWidget(QLabel('reject at:'))
        self.skySmoothCoef = QLineEdit()
        self.skySmoothCoef.setFixedSize(60, 30)
        self.skySmoothCoef.textChanged.connect(partial(self.edited, 'sky_smooth_coef'))
        hl.addWidget(self.skySmoothCoef)
        hl.addStretch(0)
        layout.addLayout(hl)

        hl = QHBoxLayout()
        calcsky = QPushButton('Calc Sky')
        calcsky.setFixedSize(120, 30)
        calcsky.clicked.connect(partial(self.sky))
        calcsky_simple = QPushButton('Calc Sky simple')
        calcsky_simple.setFixedSize(120, 30)
        calcsky_simple.clicked.connect(partial(self.sky_simple))
        hl.addWidget(calcsky)
        hl.addWidget(calcsky_simple)
        hl.addStretch(0)
        layout.addLayout(hl)
        layout.addStretch(0)
        frame.setLayout(layout)
        self.tab.addTab(frame, 'Sky model')

    def init_GUI_Correction(self):

        frame = QFrame(self)
        layout = QVBoxLayout()
        hl = QHBoxLayout()
        hl.addWidget(QLabel('Window:'))
        self.rescaleWindow = QLineEdit()
        self.rescaleWindow.setFixedSize(50, 30)
        self.rescaleWindow.textChanged.connect(partial(self.edited, 'rescale_window'))
        hl.addWidget(self.rescaleWindow)
        hl.addStretch(0)
        layout.addLayout(hl)

        hl = QHBoxLayout()
        dispersion = QPushButton('Calc dispersion')
        dispersion.setFixedSize(140, 30)
        dispersion.clicked.connect(partial(self.dispersion))
        hl.addWidget(dispersion)
        hl.addStretch(0)
        layout.addLayout(hl)

        hl = QHBoxLayout()
        rescale = QPushButton('Rescale from:')
        rescale.setFixedSize(120, 30)
        rescale.clicked.connect(partial(self.rescale))
        hl.addWidget(rescale)
        self.expResChoose = QComboBox()
        self.expResChoose.setFixedSize(250, 30)
        for s in self.parent.s:
            self.expResChoose.addItem(s.filename)
        if len(self.parent.s) > 0:
            self.exp_res_ind = self.parent.s.ind
            self.expResChoose.setCurrentIndex(self.exp_res_ind)
        self.expCrChoose.currentIndexChanged.connect(partial(self.onExpChoose, name='exp_res_ind'))
        hl.addWidget(rescale)
        hl.addWidget(self.expResChoose)
        hl.addStretch(0)
        layout.addLayout(hl)

        layout.addStretch(0)
        frame.setLayout(layout)
        self.tab.addTab(frame, 'Corrections')

    def edited(self, attr):
        try:
            setattr(self, attr, self.opts[attr][1](getattr(self, self.opts[attr][0]).text()))
        except:
            pass

    def skyModel(self):
        self.skymodeltype = self.skymodel.currentText()
        print(self.skymodeltype)

    def changeExp(self):
        self.exp_ind += 1
        if self.exp_ind >= len(self.parent.s):
            self.exp_ind = 0
        self.expchoose.setCurrentIndex(self.exp_ind)

    def onExpChoose(self, index, name='exp_ind'):
        setattr(self, name, index)

    def updateExpChoose(self):
        self.expchoose.clear()
        for s in self.parent.s:
            self.expchoose.addItem(s.filename)
        self.expchoose.setCurrentIndex(self.exp_ind)
        self.expResChoose.clear()
        for s in self.parent.s:
            self.expResChoose.addItem(s.filename)
        self.expResChoose.setCurrentIndex(self.exp_res_ind)
        self.expCrChoose.clear()
        for s in self.parent.s:
            self.expCrChoose.addItem(s.filename)
        self.expCrChoose.setCurrentIndex(self.exp_cr_ind)

    def cr(self, update='new'):

        if update in ['new', 'add']:
            kwargs = {}
            for line in self.input.toPlainText().splitlines():
                if line.split('=')[1].replace('-', '', 1).replace('.', '', 1).strip().isdigit():
                    kwargs[line.split('=')[0]] = float(line.split('=')[1])
                else:
                    kwargs[line.split('=')[0]] = line.split('=')[1]

            self.parent.s[self.exp_ind].spec2d.cr_remove(update, **kwargs)

        elif update == 'raw':
            s = self.parent.s[self.exp_ind].spec2d
            if s.cr is None:
                s.cr = image(x=s.raw.x, y=s.raw.y, mask=np.zeros_like(s.raw.z))
            if s.raw.mask is not None:
                s.cr.mask = np.logical_or(s.cr.mask, s.raw.mask)

        self.parent.s.redraw()

    def clear(self):
        self.parent.s[self.exp_ind].spec2d.cr.mask = np.zeros_like(self.parent.s[self.exp_ind].spec2d.raw.z)
        self.parent.s.redraw()

    def crfromexp(self):
        self.parent.s[self.exp_ind].spec2d.cr.mask = np.copy(self.parent.s[self.exp_cr_ind].spec2d.cr.mask)
        self.parent.s.redraw()

    def expand(self):
        self.parent.s[self.exp_ind].spec2d.expand_mask(self.exp_pixel)
        self.parent.s.redraw()

    def intelExpand(self):
        self.parent.s[self.exp_ind].spec2d.intelExpand(self.exp_factor, self.exp_pixel)
        self.parent.s.redraw()

    def clean(self):
        self.parent.s[self.exp_ind].spec2d.clean()
        self.parent.s.redraw()
        self.updateExpChoose()

    def extrapolate(self, inplace=False):
        self.parent.s[self.exp_ind].spec2d.extrapolate(inplace, self.extr_width, self.extr_height)
        self.parent.s.redraw()
        self.updateExpChoose()

    def trace(self):
        s = self.parent.s[self.exp_ind]
        inds = np.where(s.cont_mask2d)[0]

        s.spec2d.moffat_grid(2.35482 * self.extr_slit / 2 / np.sqrt(2 ** (1 / 4.765) - 1))
        for k, i in zip(np.arange(len(inds))[:-self.trace_step:self.trace_step], inds[:-self.trace_step:self.trace_step]):
            try:
                print(k)
                s.spec2d.profile(s.spec2d.raw.x[i+int(self.trace_step/2)-4], s.spec2d.raw.x[i+int(self.trace_step/2)+4],
                                 s.spec2d.raw.y[self.extr_border], s.spec2d.raw.y[-self.extr_border],
                                 x_0=s.cont2d.y[k], slit=self.extr_slit)
            except:
                pass

        self.parent.s[self.parent.s.ind].redraw()

    def trace_fit(self):
        self.parent.s[self.parent.s.ind].spec2d.fit_trace()
        self.parent.s.redraw()

    def trace_stat(self):
        trace = self.parent.s[self.parent.s.ind].spec2d.trace
        if trace is not None:
            fig, ax = plt.subplots(1, 2)
            ax[0].plot(trace[0], trace[1])
            ax[1].plot(trace[0], trace[2])
            plt.show()

    def sky(self):

        s = self.parent.s[self.exp_ind]
        s.spec2d.sky_model(s.spec2d.raw.x[0], s.spec2d.raw.x[-1], border=self.extr_border, slit=self.extr_slit,
                           model=self.skymodeltype, window=self.extr_window, poly=self.sky_poly, conf=self.extr_conf,
                           smooth=self.sky_smooth, smooth_coef=self.sky_smooth_coef)

        self.parent.s.redraw()

    def sky_simple(self):

        s = self.parent.s[self.exp_ind]
        s.spec2d.sky_model_simple(s.spec2d.raw.x[0], s.spec2d.raw.x[-1], border=self.extr_border, conf=self.extr_conf)

        self.parent.s.redraw()

    def extract(self):

        self.helio_corr = float(self.helioCorr.text()) if self.helio.isChecked() else None

        s = self.parent.s[self.exp_ind]
        s.spec2d.extract(s.spec2d.raw.x[0], s.spec2d.raw.x[-1], slit=self.extr_slit, airvac=self.airVac.isChecked(), helio=self.helio_corr)

        self.updateExpChoose()
        self.parent.s.redraw(len(self.parent.s)-1)


    def dispersion(self):
        s = self.parent.s[self.exp_ind]
        x = s.spec.x()[s.cont_mask]
        y = s.spec.y()[s.cont_mask]
        err = s.spec.err()[s.cont_mask]

        std = []
        ref = np.arange(np.sum(s.cont_mask))
        for k, i in enumerate(np.where(s.cont_mask)[0]):
            mask = np.logical_and(ref > i-self.rescale_window / 2, ref < i+self.rescale_window / 2)
            std.append(np.std(y[mask] - s.cont.y[mask]) / np.mean(err[mask]))

        self.parent.s.append(Spectrum(self.parent, 'error_dispersion', data=[s.cont.x, np.asarray(std)]))
        print(len(s.cont.x), len(std))
        self.updateExpChoose()
        self.parent.s.redraw(len(self.parent.s)-1)

    def rescale(self):
        self.exp_res_ind = self.expResChoose.currentIndex()
        s = self.parent.s[self.exp_res_ind]
        inter = interp1d(s.cont.x, s.cont.y, fill_value='extrapolate')
        s = self.parent.s[self.exp_ind]
        s.spec.raw.err *= inter(s.spec.raw.x)
        self.parent.s.redraw(self.exp_ind)

    def keyPressEvent(self, event):
        super(extract2dWidget, self).keyPressEvent(event)
        key = event.key()

        if not event.isAutoRepeat():
            if event.key() == Qt.Key_D:
                if (QApplication.keyboardModifiers() == Qt.ControlModifier):
                    self.parent.extract2dwindow.close()

    def closeEvent(self, event):
        self.parent.extract2dwindow = None
        event.accept()


class fitContWidget(QWidget):
    def __init__(self, parent):
        super(fitContWidget, self).__init__()
        self.parent = parent
        self.init_GUI()
        self.init_Parameters()
        self.setStyleSheet(open('config/styles.ini').read())
        self.setGeometry(200, 200, 550, 500)
        self.setWindowTitle('Continuum construction')

    def init_Parameters(self):
        self.opts = OrderedDict([
            ('cont_iter', ['contIter', int, 3]),
            ('cont_smooth', ['contSmooth', int, 201]),
            ('cont_clip', ['contClip', float, 3.0]),
            ('x_min', ['xmin', float, 3500]),
            ('x_max', ['xmax', float, 4500]),
            ('sg_order', ['sgOrder', int, 5])
        ])
        for opt in self.opts.keys():
            setattr(self, opt, self.opts[opt][1](self.opts[opt][2]))
            getattr(self, self.opts[opt][0]).setText(str(getattr(self, opt)))

    def init_GUI(self):
        layout = QVBoxLayout()

        self.tab = QTabWidget()
        self.tab.setGeometry(0, 0, 550, 200)
        self.tab.setMinimumSize(550, 200)
        self.tab.setCurrentIndex(0)
        self.init_GUI_Bsplain()
        self.init_GUI_SG()
        self.init_GUI_Smooth()
        self.init_GUI_Cheb()
        layout.addWidget(self.tab)

        hl = QHBoxLayout()
        hl.addWidget(QLabel('Iterations:'))
        self.contIter = QLineEdit()
        self.contIter.setFixedSize(50, 30)
        self.contIter.textChanged.connect(partial(self.edited, 'cont_iter'))
        hl.addWidget(self.contIter)
        hl.addStretch(1)
        layout.addLayout(hl)

        hl = QHBoxLayout()
        hl.addWidget(QLabel('Smooth:'))
        self.contSmooth = QLineEdit()
        self.contSmooth.setFixedSize(50, 30)
        self.contSmooth.textChanged.connect(partial(self.edited, 'cont_smooth'))
        hl.addWidget(self.contSmooth)
        hl.addStretch(1)
        layout.addLayout(hl)

        hl = QHBoxLayout()
        hl.addWidget(QLabel('Clipping:'))
        self.contClip = QLineEdit()
        self.contClip.setFixedSize(50, 30)
        self.contClip.textChanged.connect(partial(self.edited, 'cont_clip'))
        hl.addWidget(self.contClip)
        clip_group = QButtonGroup(self)
        self.positive = QRadioButton('posit.')
        self.positive.setChecked(True)
        clip_group.addButton(self.positive)
        hl.addWidget(self.positive)
        self.negative = QRadioButton('negat.')
        clip_group.addButton(self.negative)
        hl.addWidget(self.negative)
        self.absolute = QRadioButton('absol.')
        clip_group.addButton(self.absolute)
        hl.addWidget(self.absolute)
        hl.addStretch(1)
        layout.addLayout(hl)

        hl = QHBoxLayout()
        data_group = QButtonGroup(self)
        self.spectrum = QRadioButton('spectrum')
        self.spectrum.setChecked(True)
        data_group.addButton(self.spectrum)
        hl.addWidget(self.spectrum)
        self.cont = QRadioButton('continuum')
        data_group.addButton(self.cont)
        hl.addWidget(self.cont)
        hl.addStretch(1)
        layout.addLayout(hl)

        hl = QHBoxLayout()
        type_group = QButtonGroup(self)
        self.fullRange = QRadioButton('full')
        self.fullRange.setChecked(True)
        type_group.addButton(self.fullRange)
        hl.addWidget(self.fullRange)
        self.shownRange = QRadioButton('shown')
        type_group.addButton(self.shownRange)
        hl.addWidget(self.shownRange)
        self.windowRange = QRadioButton('window:')
        type_group.addButton(self.windowRange)
        hl.addWidget(self.windowRange)
        self.xmin = QLineEdit()
        self.xmin.setFixedSize(50, 30)
        self.xmin.textChanged.connect(partial(self.edited, 'x_min'))
        hl.addWidget(self.xmin)
        hl.addWidget(QLabel('..'))
        self.xmax = QLineEdit()
        self.xmax.setFixedSize(50, 30)
        self.xmax.textChanged.connect(partial(self.edited, 'x_max'))
        hl.addWidget(self.xmax)
        hl.addStretch(1)
        layout.addLayout(hl)

        hl = QHBoxLayout()
        write_group = QButtonGroup(self)
        self.new = QRadioButton('new')
        self.new.setChecked(True)
        write_group.addButton(self.new)
        hl.addWidget(self.new)
        self.add = QRadioButton('add/overwrite')
        write_group.addButton(self.add)
        hl.addWidget(self.add)
        hl.addStretch(1)
        layout.addLayout(hl)
        hl = QHBoxLayout()
        exposure = QPushButton('Exposure:')
        exposure.setFixedSize(100, 30)
        exposure.clicked.connect(self.changeExp)
        self.expchoose = QComboBox()
        self.expchoose.setFixedSize(400, 30)
        for s in self.parent.s:
            self.expchoose.addItem(s.filename)
        if len(self.parent.s) > 0:
            self.exp_ind = self.parent.s.ind
            self.expchoose.currentIndexChanged.connect(self.onExpChoose)
            self.expchoose.setCurrentIndex(self.exp_ind)
        hl.addWidget(exposure)
        hl.addWidget(self.expchoose)
        hl.addStretch(0)
        layout.addStretch(1)
        layout.addLayout(hl)
        hl = QHBoxLayout()
        fit = QPushButton('Make it')
        fit.setFixedSize(100, 30)
        fit.clicked.connect(self.fit)
        hl.addWidget(fit)
        layout.addStretch(1)
        layout.addLayout(hl)
        self.setLayout(layout)

    def init_GUI_Bsplain(self):

        frame = QFrame(self)
        layout = QVBoxLayout()

        frame.setLayout(layout)
        self.tab.addTab(frame, 'Bspline')

    def init_GUI_SG(self):

        frame = QFrame(self)
        layout = QVBoxLayout()

        hl = QHBoxLayout()
        hl.addWidget(QLabel('Order:'))
        self.sgOrder = QLineEdit()
        self.sgOrder.setFixedSize(50, 30)
        self.sgOrder.textChanged.connect(partial(self.edited, 'sg_order'))
        hl.addWidget(self.sgOrder)
        hl.addStretch(1)
        layout.addLayout(hl)

        layout.addStretch(0)
        frame.setLayout(layout)
        self.tab.addTab(frame, 'SG')

    def init_GUI_Smooth(self):

        frame = QFrame(self)
        layout = QVBoxLayout()

        hl = QHBoxLayout()
        filter = QPushButton('Filter:')
        filter.setFixedSize(100, 30)
        filter.clicked.connect(self.changeFilter)
        self.filterchoose = QComboBox()
        self.filterchoose.setFixedSize(400, 30)
        self.filternames = ['flat', 'hanning', 'hamming', 'bartlett', 'blackman']
        self.filterchoose.addItems(self.filternames)
        self.filterchoose.setCurrentIndex(0)
        hl.addWidget(filter)
        hl.addWidget(self.filterchoose)
        hl.addStretch(0)
        layout.addStretch(1)
        layout.addLayout(hl)

        frame.setLayout(layout)
        self.tab.addTab(frame, 'Smooth')

    def init_GUI_Cheb(self):

        frame = QFrame(self)
        layout = QVBoxLayout()

        frame.setLayout(layout)
        self.tab.addTab(frame, 'Chebyshev')

    def edited(self, attr):
        try:
            setattr(self, attr, self.opts[attr][1](getattr(self, self.opts[attr][0]).text()))
        except:
            pass

    def changeExp(self):
        self.exp_ind += 1
        if self.exp_ind >= len(self.parent.s):
            self.exp_ind = 0
        self.expchoose.setCurrentIndex(self.exp_ind)

    def changeFilter(self):
        ind = self.filterchoose.currentIndex() + 1 if self.filterchoose.currentIndex() < len(self.filternames)-1 else 0
        self.filterchoose.setCurrentIndex(ind)

    def onExpChoose(self, index, name='exp_ind'):
        setattr(self, name, index)

    def updateExpChoose(self):
        self.expchoose.clear()
        for s in self.parent.s:
            self.expchoose.addItem(s.filename)
        self.expchoose.setCurrentIndex(self.exp_ind)

    def fit(self):
        getattr(self, 'fit' + self.tab.tabText(self.tab.currentIndex()))()

    def fitBspline(self):
        x = self.getRange()
        self.parent.s[self.exp_ind].calcCont(method='Bspline', xl=x[0], xr=x[-1], iter=self.cont_iter, window=self.cont_smooth,
                                             clip=self.cont_clip, new=self.new.isChecked(), cont=self.cont.isChecked(), sign=self.sign())

    def fitSmooth(self):
        x = self.getRange()
        self.parent.s[self.exp_ind].calcCont(method='Smooth', xl=x[0], xr=x[-1], iter=self.cont_iter, window=self.cont_smooth,
                                             clip=self.cont_clip, filter=self.filternames[self.filterchoose.currentIndex()],
                                             new=self.new.isChecked(), cont=self.cont.isChecked(), sign=self.sign())

    def fitSG(self):
        x = self.getRange()
        self.parent.s[self.exp_ind].calcCont(method='SG', xl=x[0], xr=x[-1], iter=self.cont_iter, window=self.cont_smooth,
                                             clip=self.cont_clip, sg_order=self.sg_order, new=self.new.isChecked(),
                                             cont=self.cont.isChecked(), sign=self.sign())

    def sign(self):
        if self.positive.isChecked():
            return 1
        if self.negative.isChecked():
            return -1
        if self.absolute.isChecked():
            return 0

    def getRange(self):
        if self.fullRange.isChecked():
            x = [self.parent.s[self.exp_ind].spec.x()[0], self.parent.s[self.exp_ind].spec.x()[-1]]
        if self.shownRange.isChecked():
            x = self.parent.plot.vb.getState()['viewRange'][0]
        if self.windowRange.isChecked():
            x = [float(self.xmin.text()), float(self.xmax.text())]
        return x

    def closeEvent(self, event):
        self.parent.fitContWindow = None
        event.accept()

class SDSSentry():
    def __init__(self, name):
        self.name = name
        self.attr = ['name']

    def add_attr(self, attr):
        self.attr.append(attr)
    
    def __repr__(self):
        st = ''
        for a in self.attr:
            st += a + '=' + str(getattr(self, a)) + '\n'
        return st
        
    def __str__(self):
        return self.name
       
class loadSDSSwidget(QWidget):
    
    def __init__(self, parent):
        super(loadSDSSwidget, self).__init__()
        self.parent = parent
        self.setStyleSheet(open('config/styles.ini').read())
        self.initUI()
        
    def initUI(self):      

        splitter = QSplitter(Qt.Vertical)

        layout = QVBoxLayout(self)
        l = QHBoxLayout(self)
        l.addWidget(QLabel('Plate:', self))
        self.plate = QLineEdit(self)
        self.plate.setMaxLength(4)
        l.addWidget(self.plate)

        l.addWidget(QLabel('MJD:', self))
        self.mjd = QLineEdit(self)
        self.mjd.setMaxLength(5)
        l.addWidget(self.mjd)
        #self.MJD.move(20, 90)
        
        l.addWidget(QLabel('fiber:', self))
        self.fiber = QLineEdit(self)
        self.fiber.setMaxLength(4)
        l.addWidget(self.fiber)
        l.addStretch(1)

        l.addWidget(QLabel('or name:', self))
        self.name = QLineEdit(self)
        self.name.setMaxLength(30)
        self.name.setFixedSize(200, 30)
        l.addWidget(self.name)

        layout.addLayout(l)

        l = QHBoxLayout(self)
        self.load = QPushButton('Load', self)
        self.load.setFixedSize(150, 30)
        #self.load.resize(self.load.sizeHint())
        self.load.clicked.connect(self.loadspectrum)
        l.addWidget(self.load)
        l.addStretch(1)

        layout.addLayout(l)
        layout.addStretch(1)

        widget = QWidget()
        widget.setLayout(layout)
        splitter.addWidget(widget)

        layout = QVBoxLayout(self)
        l = QHBoxLayout(self)
        l.addWidget(QLabel('Load list:'))
        self.filename = QLineEdit(self)
        self.filename.setMaxLength(100)
        self.filename.setFixedSize(600, 30)
        l.addWidget(self.filename)
        self.choosefile = QPushButton('Choose', self)
        self.choosefile.setFixedSize(100, 30)
        self.choosefile.clicked.connect(self.chooseFile)
        l.addWidget(self.choosefile)
        l.addStretch(1)
        layout.addLayout(l)

        l = QHBoxLayout(self)
        self.DR14 = QCheckBox('DR14')
        self.DR14.clicked.connect(partial(self.selectCat, 'DR14'))
        l.addWidget(self.DR14)

        self.DR12 = QCheckBox('DR12')
        self.DR12.clicked.connect(partial(self.selectCat, 'DR12'))
        l.addWidget(self.DR12)

        self.DR9Lee = QCheckBox('DR9Lee')
        self.DR9Lee.clicked.connect(partial(self.selectCat, 'DR9Lee'))
        l.addWidget(self.DR9Lee)
        l.addStretch(1)

        grp = QButtonGroup(self)
        grp.addButton(self.DR14)
        grp.addButton(self.DR12)
        grp.addButton(self.DR9Lee)
        getattr(self, self.parent.SDSScat).setChecked(True)

        layout.addLayout(l)

        hl = QHBoxLayout(self)

        self.sdsslist = QTextEdit('#enter list in PLATE, FIBER format')
        self.sdsslist.setFixedSize(250, 500)
        hl.addWidget(self.sdsslist)

        self.listPars = QWidget(self)
        self.scrolllayout = QVBoxLayout(self.listPars)
        self.scroll = None
        self.saved = {}
        self.updateScroll()
        hl.addWidget(self.listPars)

        vl = QVBoxLayout(self)
        self.preview = QTextEdit()
        self.preview.setFixedSize(400, 500)
        vl.addWidget(self.preview)

        l = QHBoxLayout(self)
        l.addWidget(QLabel('Plate:'))
        self.plate_col = QLineEdit()
        self.plate_col.setFixedSize(40, 30)
        l.addWidget(self.plate_col)

        l.addWidget(QLabel('Fiber:'))
        self.fiber_col = QLineEdit()
        self.fiber_col.setFixedSize(40, 30)
        l.addWidget(self.fiber_col)

        l.addWidget(QLabel('Header:'))
        self.header = QLineEdit()
        self.header.setText('1')
        self.header.setFixedSize(40, 30)
        l.addWidget(self.header)
        l.addStretch(1)
        vl.addLayout(l)

        hl.addStretch(1)
        hl.addLayout(vl)

        layout.addLayout(hl)

        l = QHBoxLayout(self)
        self.loadlist = QPushButton('Load list', self)
        self.loadlist.setFixedSize(150, 30)
        # self.load.resize(self.load.sizeHint())
        self.loadlist.clicked.connect(self.loadList)
        l.addWidget(self.loadlist)
        l.addStretch(1)

        layout.addLayout(l)

        layout.addStretch(1)
        widget = QWidget()
        widget.setLayout(layout)
        splitter.addWidget(widget)

        splitter.setSizes([250, 1500])

        layout = QVBoxLayout(self)
        layout.addWidget(splitter)
        self.setLayout(layout)

        self.setGeometry(300, 300, 950, 900)
        self.setWindowTitle('load SDSS by Plate/MJD/Fiber or name')
        self.show()
        self.selectCat()

    def updateScroll(self):
        for s in self.saved.keys():
            try:
                self.scrolllayout.removeWidget(getattr(self, s))
                getattr(self, s).deleteLater()
            except:
                pass
        if self.scroll is not None:
            self.scrolllayout.removeWidget(self.scroll)
            self.scroll.deleteLater()

        self.scroll = QScrollArea()
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setWidgetResizable(True)
        #self.scroll.setMaximumHeight(self.height()-150)
        self.scrollContent = QWidget(self.scroll)
        if hasattr(self, 'data'):
            l = QVBoxLayout()
            for par in self.saved.keys():
                setattr(self, str(par), QCheckBox(str(par)))
                getattr(self, str(par)).setChecked(self.saved[par])
                getattr(self, str(par)).clicked[bool].connect(partial(self.click, str(par)))
                l.addWidget(getattr(self, str(par)))
            l.addStretch()
            self.scrollContent.setLayout(l)
            self.scroll.setWidget(self.scrollContent)
        self.scrolllayout.addWidget(self.scroll)


    def loadspectrum(self):

        plate = str(self.plate.text())
        MJD = str(self.mjd.text())
        fiber = '{:0>4}'.format(self.fiber.text())
        name = self.name.text().strip()

        if self.parent.loadSDSS(plate=plate, MJD=MJD, fiber=fiber, name=name):
            pass
            #self.close()

    def chooseFile(self):
        fname = QFileDialog.getOpenFileName(self, 'Import SDSS list', self.parent.SDSSfolder)

        if fname[0]:
            self.filename.setText(fname[0])
            self.parent.options('SDSSfolder', os.path.dirname(fname[0]))
            with open(fname[0], 'r') as f:
                try:
                    self.header.setText('1')
                    data = np.genfromtxt(self.filename.text(), names=True)
                    names = [n.lower() for n in data.dtype.names]
                    self.plate_col.setText(str(data.dtype.names.index(names.index('plate'))))
                    ind = names.index('fiber') if 'fiber' in names else names.index('fiberid')
                    self.fiber_col.setText(str(ind))
                except:
                    t = f.readlines()
                    self.preview.setPlainText(''.join(t))
                    ind = [len(s.split()) for s in t]
                    print(ind)
                    self.header.setText(str(np.argmax(ind)))

    def selectCat(self, cat=None):
        if cat != self.parent.SDSScat:
            if cat is None:
                cat = self.parent.SDSScat
            self.parent.options('SDSScat', cat)
            if cat == 'DR14':
                self.data = Table.read('C:\science\SDSS\DR14\DR14Q_v4_4.fits')
                default = ['SDSS_NAME', 'RA', 'DEC', 'PLATE', 'MJD', 'FIBERID', 'Z']
            if cat == 'DR12':
                self.data = Table(self.parent.IGMspec['BOSS_DR12']['meta'][()])
                default = ['SDSS_NAME', 'RA_GROUP', 'DEC_GROUP', 'PLATE', 'MJD', 'FIBERID', 'Z_VI']
            if cat == 'DR9Lee':
                self.data = Table.read('C:/science/SDSS/DR9_Lee/BOSSLyaDR9_cat.fits')
                default = ['SDSS_NAME', 'RA', 'DEC', 'PLATE', 'MJD', 'FIBERID', 'Z_VI']
            self.saved = {}
            for par in self.data.colnames:
                self.saved[str(par)] = par in default
            self.updateScroll()

    def click(self, s):
        self.saved[s] = getattr(self, s).isChecked()

    def loadList(self):
        pars = [k for k, v in self.saved.items() if v]

        self.parent.SDSSdata = None
        inds, fiber, plate = [], [], []
        if self.filename.text().strip() == '':
            data = np.recarray((0,), dtype=[('plate', int), ('fiber', int)])
            for line in self.sdsslist.toPlainText().splitlines():
                if not line.startswith('#'):
                    data = np.append(data, np.array([(int(line.split()[0]), int(line.split()[1]))], dtype=data.dtype))
            if data.shape[0] > 0:
                plate, fiber = data['plate'], data['fiber']
            else:
                inds = np.arange(len(self.data['PLATE']))
        else:
            data = np.genfromtxt(self.filename.text(), dtype=int, skip_header=int(self.header.text()))
            plate, fiber = data[:, int(self.plate_col.text())-1], data[:, int(self.fiber_col.text())-1]

        for p, f in zip(plate, fiber):
            print(p, f)
            ind = np.where((self.data['PLATE'] == p) * (self.data['FIBERID'] == f))[0]
            if len(ind) > 0:
                inds.append(ind[0])
            else:
                print('missing:', p, f)

        self.parent.SDSSdata = np.array(self.data[pars][inds])

        if self.parent.SDSSdata is not None:
            self.parent.SDSSlist = QSOlistTable(self.parent, 'SDSS')
            self.parent.SDSSlist.setdata(self.parent.SDSSdata)

    def keyPressEvent(self, qKeyEvent):
        if qKeyEvent.key() == Qt.Key_Return:
            self.loadspectrum()

class SDSSPhotWidget(QWidget):
    def __init__(self, parent):
        super(SDSSPhotWidget, self).__init__()
        self.parent = parent
        self.setGeometry(100, 100, 2000, 1100)
        self.setStyleSheet(open('config/styles.ini').read())
        self.show()

class ShowListImport(QWidget):
    def __init__(self, parent, cat=''):
        super().__init__()
        self.parent = parent

        self.move(400, 100)
        self.setStyleSheet(open('config/styles.ini').read())
        self.table = QSOlistTable(self.parent, cat=cat, subparent=self, editable=False)
        self.table.setSelectionMode(QAbstractItemView.MultiSelection)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)

        self.loadallButton = QPushButton("Show all")
        self.loadallButton.setFixedSize(90, 30)
        self.loadallButton.clicked[bool].connect(self.loadall)
        
        self.loadButton = QPushButton("Show")
        self.loadButton.setFixedSize(90, 30)
        self.loadButton.clicked[bool].connect(self.load)
        self.cancelButton = QPushButton("Cancel")
        self.cancelButton.setFixedSize(90, 30)
        self.cancelButton.clicked[bool].connect(self.close)
        hbox = QHBoxLayout()
        hbox.addWidget(self.loadallButton)
        hbox.addStretch(1)
        hbox.addWidget(self.loadButton)
        hbox.addWidget(self.cancelButton)
        
        layout = QVBoxLayout()
        layout.addWidget(self.table)
        layout.addLayout(hbox)
        self.setLayout(layout)
        
    def setdata(self, data):
        self.table.setdata(data)
        self.resize(self.width(), self.table.rowCount()*40+210)

    def load(self, loadall=False):
        flist = set(self.table.item(index.row(),0).text() for index in self.table.selectedIndexes())
        print(flist)
        with open(self.parent.importListFile) as f:
            if loadall:
                flist = f.read().splitlines()
            self.parent.importSpectrum(flist, dir_path=os.path.dirname(self.parent.importListFile)+'/')

    def loadall(self):
        self.load(loadall=True)


class ShowListCombine(QWidget):
    def __init__(self, parent, cat=''):
        super().__init__()
        self.parent = parent

        self.setStyleSheet(open('config/styles.ini').read())
        self.table = QSOlistTable(self.parent, cat=cat, subparent=self, editable=False)
        self.table.setSelectionMode(QAbstractItemView.MultiSelection)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)

        layout = QVBoxLayout()
        layout.addWidget(self.table)
        self.setLayout(layout)
        self.setWidth = None

        self.update()
        self.show()

    def update(self):
        dtype = [('filename', np.str_, 100), ('obs. date', np.str_, 30),
                 ('wavelmin', np.float_), ('wavelmax', np.float_),
                 ('resolution', np.int_)]
        zero = ('', '', np.nan, np.nan, 0)
        data = np.array([zero], dtype=dtype)
        self.edit_col = [4]
        for s in self.parent.parent.s:
            print(s.filename, s.date, s.wavelmin, s.wavelmax, s.resolution)
            data = np.insert(data, len(data), np.array(
                [('  ' + s.filename + '  ', '  ' + s.date + '  ', s.wavelmin, s.wavelmax, s.resolution)],
                dtype=dtype), axis=0)
        data = np.delete(data, (0), axis=0)
        self.table.setdata(data)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setResizeMode(1, QHeaderView.ResizeToContents)
        if self.setWidth is None:
            self.setWidth = 120 + self.table.verticalHeader().width() + self.table.autoScrollMargin() * 2.5
            self.setWidth += np.sum([self.table.columnWidth(c) for c in range(self.table.columnCount())])
        self.table.resize(self.setWidth, self.table.rowCount() * 40 + 140)


class ExportDataWidget(QWidget):
    def __init__(self, parent, type):
        super().__init__()
        self.parent = parent
        self.type = type
        if self.type in ['export', 'export2d']:
            try:
                self.filename = self.parent.s[self.parent.s.ind].filename
            except:
                self.filename = None
        if self.type == 'save':
            self.filename = self.parent.options('filename_saved')
        self.initUI()
        
    def initUI(self):

        layout = QVBoxLayout()

        lbl = QLabel('filename:')
        self.setfilename = QLineEdit(self.filename)
        self.setfilename.resize(600, 25)
        self.setfilename.textChanged[str].connect(self.filenameChanged)

        self.chooseFile = QPushButton("Get file")
        self.chooseFile.clicked[bool].connect(self.chooseFileName)
        self.chooseFile.setFixedSize(70, 30)
        hbox_file = QHBoxLayout()
        hbox_file.addWidget(lbl)
        hbox_file.addWidget(self.setfilename)
        hbox_file.addWidget(self.chooseFile)
        #hbox_file.addStretch(1)
        layout.addLayout(hbox_file)

        if self.type == 'export':
            self.check = OrderedDict([('spectrum', 'Spectrum'), ('cont', 'Continuum'),
                                      ('fit', 'Fit model'), ('lines', 'Lines')])
            self.opt = self.parent.export_opt
        elif self.type == 'save':
            self.check = OrderedDict([('spectrum', 'Spectrum'), ('cont', 'Continuum'),
                                      ('points', 'Selected points'), ('fit', 'Fit model'),
                                      ('others', 'Other data'), ('fit_results', 'Fit results')])
            self.opt = self.parent.save_opt
        elif self.type == 'export2d':
            self.check = OrderedDict([('spectrum', 'Spectrum'), ('err', 'Error'),
                                      ('mask', 'Masked values'), ('cr', 'Cosmic Ray mask'),
                                      ('sky', 'Sky model'), ('trace', 'Trace')])
            self.opt = self.parent.export2d_opt

        for k, v in self.check.items():
            setattr(self, k, QCheckBox(v))
            if k in self.opt:
                getattr(self, k).setChecked(True)
            layout.addWidget(getattr(self, k))

        for k, v in self.check.items():
            getattr(self, k).stateChanged.connect(self.onChanged)

        if self.type == 'export':
            hbox = QHBoxLayout()
            hbox.addWidget(QLabel('wavelenghts units:  '))
            self.wave_units = ['angstr', 'nm']
            self.waveunit = 'angstr'
            for s in self.wave_units:
                setattr(self, s, QCheckBox(s))
                getattr(self, s).clicked[bool].connect(partial(self.waveChanged, s))
                hbox.addWidget(getattr(self, s))
            self.waveChanged(self.waveunit)
            hbox.addStretch(1)
            layout.addLayout(hbox)

        self.okButton = QPushButton(self.type.title())
        self.okButton.clicked[bool].connect(getattr(self, self.type))
        self.okButton.setFixedSize(80, 30)
        self.cancelButton = QPushButton("Cancel")
        self.cancelButton.clicked[bool].connect(self.close)
        self.cancelButton.setFixedSize(80, 30)
        hbox = QHBoxLayout()
        hbox.addStretch(1)
        hbox.addWidget(self.okButton)
        hbox.addWidget(self.cancelButton)
        
        layout.addStretch(1)
        layout.addLayout(hbox)
        self.setLayout(layout)
        
        self.setGeometry(200, 200, 800, 350)
        self.setWindowTitle(self.type.title() + ' Data')
        self.setStyleSheet(open('config/styles.ini').read())
        self.show()
        
    def filenameChanged(self, text):
        try:
            self.filename = text
        except:
            pass
    
    def chooseFileName(self):
        fname = QFileDialog.getSaveFileName(self, 'Export spectrum', self.parent.work_folder)
        if fname[0]:
            self.filename = fname[0]
            self.setfilename.setText(self.filename)
            self.parent.options('filename_saved', self.filename)
            self.parent.options('work_folder', os.path.dirname(self.filename))
            self.parent.statusBar.setText('Filename is set' + self.filename)

    def onChanged(self):
        self.opt = []
        for k in self.check.keys():
            if getattr(self, k).isChecked():
                self.opt.append(k)

    def waveChanged(self, unit):
        self.waveunit = unit
        for s in self.wave_units:
            getattr(self, s).setChecked(False)
        getattr(self, unit).setChecked(True)

    def export(self):
        s = self.parent.s[self.parent.s.ind]
        kwargs = {'fmt':'%.5f', 'delimiter': ' '}
        unit = 1
        if self.waveunit == 'nm':
            unit = 10

        if self.spectrum.isChecked():
            np.savetxt(self.filename, np.c_[s.spec.x() / unit, s.spec.y(), s.spec.err()], **kwargs)
        if self.cont.isChecked():
            np.savetxt('_cont.'.join(self.filename.rsplit('.', 1)), np.c_[s.cont.x / unit, s.cont.y], **kwargs)
        if self.fit.isChecked():
            np.savetxt('_fit.'.join(self.filename.rsplit('.', 1)), np.c_[s.fit.x() / unit, s.fit.y()], **kwargs)
        if self.lines.isChecked():
            np.savetxt('_fit_comps.'.join(self.filename.rsplit('.', 1)), np.column_stack([s.fit.x() / unit] + [c.y() for c in s.fit_comp]), **kwargs)

    def save(self):
        self.parent.save_opt = self.opt
        self.parent.saveFile(self.filename)
        self.parent.options('filename_saved', self.filename)
        self.close()

    def export2d(self):
        self.parent.export2dSpectrum(self.filename, self.opt)

    def closeEvent(self, event):
        self.parent.save_opt = self.opt


class combineWidget(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.resize(1800, 1000)
        self.move(200, 100)
        self.setStyleSheet(open('config/styles.ini').read())

        layout = QVBoxLayout()
        l = QHBoxLayout()

        vbox = QVBoxLayout()
        hbox = QHBoxLayout()
        hbox.addWidget(QLabel('combine type: '))
        self.selectcombtype = QComboBox(self)
        self.selectcombtype.addItems(['Weighted mean', 'Median', 'Mean'])
        self.selectcombtype.setFixedSize(150, 30)
        self.selectcombtype.setCurrentIndex(0)
        hbox.addWidget(self.selectcombtype)
        hbox.addStretch(1)
        vbox.addLayout(hbox)
        vbox.addWidget(QLabel('wavelength scale: '))

        self.tab = QTabWidget()
        self.tab.setGeometry(0, 0, 550, 200)
        self.tab.setMinimumSize(550, 200)
        self.addItems()
        self.tab.setCurrentIndex(2)
        vbox.addWidget(self.tab)
        vbox.addStretch(1)
        l.addLayout(vbox)

        #self.expListView = QSOlistTable(self.parent, cat='fits', subparent=self, editable=False)
        self.expListView = ShowListCombine(self, cat='fits')
        l.addWidget(self.expListView)

        self.selectallButton = QPushButton("Select all")
        self.selectallButton.setFixedSize(90, 30)
        self.selectallButton.clicked[bool].connect(self.selectall)

        self.combineButton = QPushButton("Combine")
        self.combineButton.setFixedSize(90, 30)
        self.combineButton.clicked[bool].connect(self.combine)
        self.cancelButton = QPushButton("Cancel")
        self.cancelButton.setFixedSize(90, 30)
        self.cancelButton.clicked[bool].connect(self.close)
        hbox = QHBoxLayout()
        hbox.addWidget(self.combineButton)
        hbox.addStretch(1)
        hbox.addWidget(self.selectallButton)
        #hbox.addWidget(self.cancelButton)

        layout.addLayout(l)
        layout.addLayout(hbox)
        self.setLayout(layout)

    def addItems(self):
        self.frames = ['Merged', 'Bin', 'Resolution', 'Log-linear', 'Load']
        self.tab.addTab(QFrame(self), 'Merged')

        frame = QFrame(self)
        l = QGridLayout()
        self.binsize = QLineEdit('0.025')
        l.addWidget(QLabel('Bin size, A:'), 0, 0)
        l.addWidget(self.binsize, 0, 1)
        l.addWidget(QLabel('First bin, A:'), 1, 0)
        firstbin = self.parent.s[self.parent.s.ind].spec.x()[0]
        self.zeropoint_bin = QLineEdit(str(firstbin))
        l.addWidget(self.zeropoint_bin, 1, 1)
        frame.setLayout(l)

        self.tab.addTab(frame, 'Bin')

        frame = QFrame(self)
        l = QGridLayout()
        l.addWidget(QLabel('Resolution: '), 0, 0)
        self.resolution = QLineEdit(str(int(self.parent.s[0].resolution)))
        l.addWidget(self.resolution, 0, 1)
        l.addWidget(QLabel('pixels pe FWHM: '), 1, 0)
        self.pp_fwhm = QLineEdit('3')
        l.addWidget(self.pp_fwhm, 1, 1)
        l.addWidget(QLabel('First bin, A:'), 2, 0)
        firstbin = self.parent.s.minmax()[0]
        self.zeropoint_res = QLineEdit(str(firstbin))
        l.addWidget(self.zeropoint_res, 2, 1)
        frame.setLayout(l)

        self.tab.addTab(frame, 'Resolution')

        frame = QFrame(self)
        l = QGridLayout()
        self.binsize_log = QLineEdit('0.0001')
        l.addWidget(QLabel('Bin size, in log A:'), 0, 0)
        l.addWidget(self.binsize_log, 0, 1)
        l.addWidget(QLabel('First bin, A:'), 1, 0)
        firstbin = self.parent.s.minmax()[0]
        self.zeropoint_log = QLineEdit(str(firstbin))
        l.addWidget(self.zeropoint_log, 1, 1)
        frame.setLayout(l)

        self.tab.addTab(frame, 'Log-linear')

        frame = QFrame(self)

        l = QHBoxLayout()
        self.file = QLineEdit('')
        self.file.setFixedHeight(30)
        l.addWidget(self.file)
        self.fromfile = QPushButton('load from file', self)
        self.fromfile.setFixedSize(130, 30)
        self.fromfile.clicked[bool].connect(self.loadfromfile)
        l.addWidget(self.fromfile)
        frame.setLayout(l)

        self.tab.addTab(frame, 'File')

    def loadfromfile(self):
        fname = QFileDialog.getOpenFileName(self, 'Import wavelength scale', '')

        if fname[0]:
            self.file.setText(fname[0])
            self.file_grid = np.genfromfile(fname[0], unpack=True, usecols=(0))

    def selectall(self):
        for i in range(len(self.parent.s)):
            self.expListView.table.selectRow(i)

    def combine(self):
        try:
            print([i.row() for i in self.expListView.table.selectionModel().selectedRows()])
            slist = [self.parent.s[i.row()] for i in self.expListView.table.selectionModel().selectedRows()]
        except:
            slist = self.parent.s
        print('slist:', len(slist))

        # make unified wavelength grid:
        if self.tab.currentIndex() == 0:
            x = set()
            for s in slist:
                print(len(s.spec.x()[np.logical_not(s.bad_mask.x())]))
                x.update(list(s.spec.x()[np.logical_not(s.bad_mask.x())]))
            x = sorted(x)
            x = np.asarray(x)

        elif self.tab.currentIndex() == 1:
            zero, binsize = float(self.zeropoint_bin.text()), float(self.binsize.text())
            num = int((self.parent.s.minmax()[1] - zero) / binsize)
            x = np.linspace(zero, zero + (num + 1) * binsize, num)

        elif self.tab.currentIndex() == 2:
            print('fixed res')
            zero = np.log10(float(self.zeropoint_res.text()))
            step = np.log10(1 + 1 / float(self.resolution.text()) / float(self.pp_fwhm.text()))
            print(zero, step)
            num = int((np.log10(self.parent.s.minmax()[1]) - zero) / step)
            print(num)
            x = np.logspace(zero, zero + step * (num - 1), num)

        elif self.tab.currentIndex() == 3:
            zero = np.log10(float(self.zeropoint_log.text()))
            step = float(self.binsize_log.text())
            num = int((np.log10(self.parent.s.minmax()[1]) - zero) / step)
            x = np.logspace(zero, zero + step * (num - 1), num)

        elif self.tab.currentIndex() == 4:
            x = self.file_grid

        print('x: ', len(x), x)
        # calculate combined spectrum:
        comb = np.empty([len(slist), len(x)], dtype=np.float)
        comb.fill(np.nan)
        e_comb = np.empty([len(slist), len(x)], dtype=np.float)
        e_comb.fill(np.nan)

        for i, s in enumerate(slist):
            if 0:
                if 1:
                    spec = s.spec.y()[:]
                    spec[s.bad_mask.x()] = np.NaN
                    spec = interp1d(s.spec.x(), spec, bounds_error=False, fill_value=np.NaN)
                    err = s.spec.err()[:]
                    err[s.bad_mask.x()] = np.NaN
                    err = interp1d(s.spec.x(), err, bounds_error=False, fill_value=np.NaN)
                else:
                    spec = interp1d(s.spec.x()[np.logical_not(s.bad_mask.x())], s.spec.y()[np.logical_not(s.bad_mask.x())], bounds_error=False, fill_value=np.NaN)
                    err = interp1d(s.spec.x()[np.logical_not(s.bad_mask.x())], s.spec.err()[np.logical_not(s.bad_mask.x())], bounds_error=False, fill_value=np.NaN)
                comb[i] = spec(x)
                e_comb[i] = np.power(err(x), -1)
            else:
                #print(spectres.spectres(s.spec.x(), s.spec.y(), x, spec_errs=s.spec.err()))
                mask = np.logical_and(x > s.spec.x()[2], x < s.spec.x()[-3])
                print(s.spec.x(), x[mask])
                comb[i][mask], e_comb[i][mask] = spectres.spectres(s.spec.x(), s.spec.y(), x[mask], spec_errs=s.spec.err())

        print(comb, e_comb)

        typ = self.selectcombtype.currentText()
        print(typ)
        if typ == 'Median':
            y = np.nanmedian(comb, axis=0)
            err = np.power(np.nansum(np.power(e_comb, -2), axis=0), -0.5)

        if typ == 'Mean':
            y = np.nanmean(comb, axis=0)
            err = np.power(np.nansum(np.power(e_comb, -2), axis=0), -0.5)

        if typ == 'Weighted mean':
            w = np.power(e_comb, -2)
            y = np.nansum(comb * w, axis=0) / np.nansum(w, axis=0)
            err = np.power(np.nansum(w, axis=0), -0.5)
            #err = np.power(np.nansum(np.power(e_comb, -2), axis=0), -0.5)

        mask = np.logical_not(np.isnan(y))
        x, y, err = x[mask], y[mask], err[mask]
        # add combined spectrum to GU
        print(x, y, err)
        self.parent.s.append(Spectrum(self.parent, name='combined_'+typ.split()[0].lower()))
        self.parent.s[-1].set_data([x, y, err])
        self.parent.s.setSpec(new=True)


class rebinWidget(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.resize(700, 500)
        self.move(400, 100)
        self.setStyleSheet(open('config/styles.ini').read())

        self.treeWidget = QTreeWidget()
        self.treeWidget.setHeaderHidden(True)
        self.addItems(self.treeWidget)
        self.treeWidget.setColumnCount(3)
        self.treeWidget.setColumnWidth(0, 200)
        
        self.expchoose = QComboBox(self)
        for s in self.parent.s:
            self.expchoose.addItem(s.filename)
        print(self.parent.s.ind)
        self.expchoose.setCurrentIndex(self.parent.s.ind)
        self.expchoose.currentIndexChanged.connect(self.onExpChoose)

        self.okButton = QPushButton("Rebin")
        self.okButton.setFixedSize(70, 30)
        self.okButton.clicked[bool].connect(self.rebin)
        self.cancelButton = QPushButton("Cancel")
        self.cancelButton.setFixedSize(70, 30)
        self.cancelButton.clicked[bool].connect(self.close)
        hbox = QHBoxLayout()
        hbox.addWidget(self.expchoose)
        hbox.addStretch(1)
        hbox.addWidget(self.okButton)
        hbox.addWidget(self.cancelButton)
        
        layout = QVBoxLayout()
        layout.addWidget(self.treeWidget)
        layout.addLayout(hbox)
        self.setLayout(layout)
        self.exp_ind = self.parent.s.ind
        
    def addItems(self, parent):
        self.d = {'fixednumber': 'Merge bins', 'fixedscale': 'Fixed scale', 'fixedres': 'Fixed Resolution',
             'loglinear': 'Log-linear scale', 'fromexp': 'From exposure', 'fromfile' : 'From file', 'convolve': 'Convolve'}
        for k, v in self.d.items():
            setattr(self, k+'_item', self.addParent(parent, v))
            #getattr(self, k+'_item').itemExpanded[bool].connect(partial(self.collapseAll, k))

        #self.fixednumber_item = self.addParent(parent, 'Merge bins', expanded=True)
        #self.fixedscale_item = self.addParent(parent, 'Fixed scale')
        #self.fixedres_item = self.addParent(parent, 'Fixed Resolution')
        #self.loglinear_item = self.addParent(parent, 'Log-linear scale')
        #self.fromfile_item = self.addParent(parent, 'From file')
        #self.convolve_item = self.addParent(parent, 'Convolve')
        
        self.addChild(self.fixednumber_item, 0, 'binnum', 'Bin number', 2)

        firstbin = self.parent.s[self.parent.s.ind].spec.x()[0] if len(self.parent.s) > 0 else 0
        self.addChild(self.fixedscale_item, 0, 'binsize', 'Bin size, A', 0.025)
        self.addChild(self.fixedscale_item, 1, 'zeropoint_bin', 'First bin, A', firstbin)
        
        self.addChild(self.fixedres_item, 0, 'resolution', 'Resolution', 50000)
        self.addChild(self.fixedres_item, 1, 'pp_fwhm', 'pixels per FWHM', 3)
        self.addChild(self.fixedres_item, 2, 'zeropoint_res', 'First bin, A', firstbin)
        
        self.addChild(self.loglinear_item, 0, 'binsize_log', 'step', 0.0001)
        self.addChild(self.loglinear_item, 1, 'zeropoint_log', 'First bin', np.log10(firstbin))

        self.fromexpchoose = QComboBox(self)
        for s in self.parent.s:
            self.fromexpchoose.addItem(s.filename)
        self.fromexpchoose.setCurrentIndex(self.parent.s.ind)
        item = QTreeWidgetItem(self.fromexp_item, [''])
        self.treeWidget.setItemWidget(item, 2, self.fromexpchoose)

        self.fromfile = QPushButton('Load from file', self)
        self.fromfile.clicked[bool].connect(self.loadfromfile)
        item = QTreeWidgetItem(self.fromfile_item, [''])
        ##item = QTreeWidgetItem(self.fromfile, )
        self.treeWidget.setItemWidget(item, 1, self.fromfile)

        self.addChild(self.convolve_item, 0, 'resol', 'Resolution', 50000)
        self.addChild(self.convolve_item, 1, 'res_b', 'FWHM [km/s]', 6)

        self.resol.textEdited.connect(partial(self.setResolution, 'resol'))
        self.res_b.textEdited.connect(partial(self.setResolution, 'res_b'))

        self.treeWidget.itemExpanded.connect(self.collapseAll)
        
    def addParent(self, parent, text, checkable=False, expanded=False):
        item = QTreeWidgetItem(parent, [text])
        if checkable:
            item.setCheckState(0, Qt.Unchecked)
        else:
            #item.setFlags(item.flags() | Qt.ItemIsEditable)
            item.setFlags(item.flags() & ~Qt.ItemIsUserCheckable)
        item.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)
        item.setExpanded(expanded)
        return item
        
    def addChild(self, parent, column, name, title, data):
        item = QTreeWidgetItem(parent, [title])
        setattr(self, name, QLineEdit())
        self.treeWidget.setItemWidget(item, 1, getattr(self, name))
        getattr(self, name).setText(str(data))
        #item.setData(1, Qt.UserRole, data)
        return item

    def collapseAll(self, excl):
        for k, v in self.d.items():
            if getattr(self, k+'_item') is not excl:
                self.treeWidget.collapseItem(getattr(self, k+'_item'))

    def setResolution(self, item):
        print(item)
        if item == 'resol':
            self.res_b.setText('{:.3f}'.format(299792.45 / float(self.resol.text())))
        elif item == 'res_b':
            self.resol.setText('{:.1f}'.format(299792.45 / float(self.res_b.text())))

    def loadfromfile(self):
        fname = QFileDialog.getOpenFileName(self, 'Import instrument function', '')

        if fname[0]:
            self.parent.instr_function = np.genfromfile(fname[0], unpack=True)
            
    def onExpChoose(self, index):
        self.exp_ind = index
        firstbin = self.parent.s[self.exp_ind].spec.x()[0]
        self.zeropoint_bin.setText(str(firstbin))
        self.zeropoint_res.setText(str(firstbin))
        self.zeropoint_log.setText(str(np.log10(firstbin)))

    def rebin_arr(self, a, factor):
        n = a.shape[0] // factor
        return a[:n*factor].reshape(a.shape[0] // factor, factor).sum(1)/factor 
    
    def rebin_err(self, a, factor):
        n = a.shape[0] // factor
        a = np.power(a[:n*factor].reshape(a.shape[0] // factor, factor), 2)
        return np.sqrt(a.sum(1))

    def rebin(self):
        if self.fixednumber_item.isExpanded():
            n = int(self.binnum.text())
            x = self.rebin_arr(self.parent.s[self.exp_ind].spec.x(), n)
            y = self.rebin_arr(self.parent.s[self.exp_ind].spec.y(), n)
            print(self.parent.s[self.exp_ind].spec.err()/self.parent.s[self.exp_ind].spec.y())
            err = y / self.rebin_err(self.parent.s[self.exp_ind].spec.y()/self.parent.s[self.exp_ind].spec.err(), n)
            
            self.parent.s.append(Spectrum(self.parent, name='rebinned '+str(self.exp_ind+1), data=[x, y, err]))

        elif self.fixedscale_item.isExpanded():
            zero, binsize = float(self.zeropoint_bin.text()), float(self.binsize.text())
            num = int((self.parent.s[self.exp_ind].spec.x()[-1] - zero) / binsize)
            x = np.linspace(zero, zero + (num+1) * binsize, num)
            y, err = spectres.spectres(self.parent.s[self.exp_ind].spec.raw.x, self.parent.s[self.exp_ind].spec.raw.y, x,
                                                         spec_errs=self.parent.s[self.exp_ind].spec.raw.err)

            self.parent.s.append(Spectrum(self.parent, name='rebinned '+str(self.exp_ind+1), data=[x, y, err]))
            self.parent.s[-1].Resolution = np.median(self.parent.s[-1])/(float(self.binsize.text()) * 2.5)

        elif self.fixedres_item.isExpanded():
            print('fixed res')
            zero = np.log10(float(self.zeropoint_res.text()))
            step = np.log10(1 + 1 / float(self.resolution.text()) / float(self.pp_fwhm.text()))
            print(zero, step)
            num = int((np.log10(self.parent.s[self.exp_ind].spec.x()[-1]) - zero) / step)
            print(num)
            x = np.logspace(zero, zero+step*(num-1), num)
            y, err = spectres.spectres(self.parent.s[self.exp_ind].spec.raw.x, self.parent.s[self.exp_ind].spec.raw.y, x,
                              spec_errs=self.parent.s[self.exp_ind].spec.raw.err)

            self.parent.s.append(Spectrum(self.parent, name='rebinned '+str(self.exp_ind+1)))
            self.parent.s[-1].set_data([x, y, err])
            self.parent.s[-1].resolution = float(self.resolution.text())

        elif self.loglinear_item.isExpanded():
            print('loglinear')

        elif self.fromexp_item.isExpanded():

            ind = self.fromexpchoose.currentIndex()
            lmin = np.max([self.parent.s[ind].spec.raw.x[0], self.parent.s[self.exp_ind].spec.raw.x[0]])
            lmax = np.min([self.parent.s[ind].spec.raw.x[-1], self.parent.s[self.exp_ind].spec.raw.x[-1]])
            mask = np.logical_and(self.parent.s[self.exp_ind].spec.raw.x >= lmin, self.parent.s[self.exp_ind].spec.raw.x <= lmax)
            mask_r = np.logical_and(self.parent.s[ind].spec.raw.x >= self.parent.s[self.exp_ind].spec.raw.x[mask][0],
                                    self.parent.s[ind].spec.raw.x <= self.parent.s[self.exp_ind].spec.raw.x[mask][-1])
            x = self.parent.s[ind].spec.raw.x[mask_r][1:-1]
            y, err = spectres(self.parent.s[self.exp_ind].spec.raw.x[mask], self.parent.s[self.exp_ind].spec.raw.y[mask],
                                       x, spec_errs=self.parent.s[self.exp_ind].spec.raw.err[mask])
            self.parent.s.append(Spectrum(self.parent, name='rebinned '+str(self.exp_ind+1)))
            self.parent.s[-1].set_data([x, y, err])

        elif self.fromfile_item.isExpanded():
            print('from file')

        elif self.convolve_item.isExpanded():
            x = self.parent.s[self.exp_ind].spec.x()
            print(float(self.resol.text()))
            self.parent.s.append(Spectrum(self.parent, name='convolved ' + str(self.exp_ind + 1)))
            y = convolveflux(x, self.parent.s[self.exp_ind].spec.y(), res=float(self.resol.text()), kind='direct')
            if self.parent.s[self.exp_ind].spec.raw.err is not None and self.parent.s[self.exp_ind].spec.raw.err.shape[0] == x.shape[0]:
                err = convolveflux(x, self.parent.s[self.exp_ind].spec.err(), res=float(self.resol.text()), kind='direct')
                self.parent.s[-1].set_data([x, y, err])
            else:
                self.parent.s[-1].set_data([x, y])
            if self.parent.s[self.exp_ind].resolution not in [0, None]:
                self.parent.s[-1].resolution = 1 / np.sqrt(1 / float(self.resol.text())**2 + 1 / self.parent.s[self.exp_ind].resolution**2)
            else:
                self.parent.s[-1].resolution = float(self.resol.text())

        self.parent.s.redraw()
        self.parent.s[-1].specClicked()
        self.close()

class GenerateAbsWidget(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.setGeometry(300, 200, 400, 600)
        self.setWindowTitle('Generate Absorption System:')
        self.setStyleSheet(open('config/styles.ini').read())
        self.initData()
        self.initGUI()

    def initData(self):
        self.opts = {'gen_template': str, 'gen_z': float, 'gen_xmin': float, 'gen_xmax': float,
                     'gen_resolution': float, 'gen_lyaforest': float, 'gen_Av': float, 'gen_z_Av': float,
                     'gen_snr': float
                     }
        for opt, func in self.opts.items():
            # print(opt, self.parent.options(opt), func(self.parent.options(opt)))
            setattr(self, opt, func(self.parent.options(opt)))

    def initGUI(self):
        layout = QVBoxLayout()
        grid = QGridLayout()

        validator = QDoubleValidator()
        locale = QLocale('C')
        validator.setLocale(locale)
        # validator.ScientificNotation
        names = ['Template:', '', '', '',
                 'z:', '', '', '',
                 'x_min:', '', 'x_max:', '',
                 'resolution:', '', '', '',
                 'Lya-forest:', '', '', '',
                 'Extinction: Av:', '', 'z_Av:', '',
                 'noize', '', 'SNR:', ''
                 ]
        positions = [(i, j) for i in range(7) for j in range(4)]

        for position, name in zip(positions, names):
            if name == '':
                continue
            grid.addWidget(QLabel(name), *position)

        self.opt_but = OrderedDict([('gen_z', [1, 1]), ('gen_xmin', [2, 1]), ('gen_xmax', [2, 3]),
                                    ('gen_resolution', [3, 1]), ('gen_lyaforest', [4, 1]),
                                    ('gen_Av', [5, 1]), ('gen_z_Av', [5, 3]),
                                    ('gen_snr', [6, 3])
                                    ])
        for opt, v in self.opt_but.items():
            b = QLineEdit(str(getattr(self, opt)))
            b.setFixedSize(100, 30)
            b.setValidator(validator)
            b.textChanged[str].connect(partial(self.onChanged, attr=opt))
            grid.addWidget(b, v[0], v[1])

        self.template = QComboBox(self)
        templist = ['Slesing', 'VanDenBerk', 'HST', 'const', 'spectrum']
        self.template.addItems(templist)
        ind = templist.index(self.gen_template) if self.gen_template in templist else 0
        self.template.setCurrentIndex(ind)
        grid.addWidget(self.template, 0, 1)

        self.snr = QCheckBox('SNR')
        self.snr.setChecked(True)
        grid.addWidget(self.snr, 6, 2)

        layout.addLayout(grid)
        layout.addStretch(1)

        l = QHBoxLayout()
        self.okButton = QPushButton("Generate")
        self.okButton.clicked[bool].connect(self.generate)
        self.okButton.setFixedSize(100, 30)
        self.cancelButton = QPushButton("Cancel")
        self.cancelButton.clicked[bool].connect(self.close)
        self.cancelButton.setFixedSize(100, 30)
        l.addStretch(1)
        l.addWidget(self.okButton)
        l.addWidget(self.cancelButton)
        layout.addLayout(l)

        self.setLayout(layout)

        self.show()

    def onChanged(self, text, attr=None):
        if attr is not None:
            setattr(self, attr, self.opts[attr](text))

    def generate(self):
        snr = self.gen_snr if self.snr.isChecked() else None
        self.parent.generate(template=self.template.currentText(), z=self.gen_z,
                             xmin=self.gen_xmin, xmax=self.gen_xmax,
                             resolution=self.gen_resolution, snr=snr, lyaforest=self.gen_lyaforest,
                             Av=self.gen_Av, z_Av=self.gen_z_Av)

        self.close()

    def closeEvent(self, ev):
        for opt, func in self.opts.items():
            self.parent.options(opt, func(getattr(self, opt)))
        ev.accept()

class infoWidget(QWidget):
    def __init__(self, parent, title, file=None, text=None):
        super().__init__()
        self.parent = parent
        self.title = title
        self.file = file
        self.setWindowTitle(title)
        self.resize(700, 500)
        self.move(400, 100)

        layout = QVBoxLayout()
        self.text = QTextEdit()

        self.loadtxt(text=text)
        #self.text.setUpdatesEnabled(False)
        #self.text.setFixedSize(400, 300)

        hbox = QHBoxLayout()
        hbox.addStretch(1)
        self.okButton = QPushButton("Ok")
        self.okButton.setFixedSize(60, 30)
        self.okButton.clicked[bool].connect(self.close)
        hbox.addWidget(self.okButton)
        layout.addWidget(self.text)
        layout.addLayout(hbox)
        self.setLayout(layout)
        self.setStyleSheet(open('config/styles.ini').read())

    def loadtxt(self, text=None):
        if text is None:
            with open(self.file) as f:
                text = f.read()

        self.text.setText(text)

class buttonpanel(QFrame):
    def __init__(self, parent):
        super().__init__()
        
        self.parent = parent
        self.initUI()

    def initUI(self):
        # >>> Redshift button
        lbl = QLabel('z =', self)
        lbl.move(30, 25)

        self.z_panel = QLineEdit(self)
        self.z_panel.move(55, 20)
        self.z_panel.textChanged[str].connect(self.zChanged)
        self.z_panel.setMaxLength(12)
        self.z_panel.resize(120, 30)
        validator = QDoubleValidator()
        validator.setLocale(QLocale('C'))
        self.z_panel.setValidator(validator)

        # >>> Normalized button
        self.normalize = QPushButton('Normalize', self)
        self.normalize.setCheckable(True)
        self.normalize.clicked[bool].connect(self.parent.normalize)
        self.normalize.move(180, 20)
        self.normalize.resize(110, 30)

        self.fitbutton = QPushButton('Fit', self)
        self.fitbutton.setCheckable(True)
        self.fitbutton.clicked.connect(self.parent.fitLM)
        self.fitbutton.setStyleSheet('QPushButton::checked { background-color: rgb(168,66,195);}')
        self.fitbutton.move(300, 20)
        self.fitbutton.resize(70, 30)

        self.SAS = QPushButton('SAS', self)
        self.SAS.clicked.connect(partial(self.openURL, 'SAS'))
        self.SAS.move(450, 20)
        self.SAS.resize(70, 30)

        self.SkyS = QPushButton('SkyS', self)
        self.SkyS.clicked.connect(partial(self.openURL, 'SkyS'))
        self.SkyS.move(530, 20)
        self.SkyS.resize(70, 30)

    def initStyle(self):
        self.setStyleSheet("""
            QFrame {
                border: 1px solid  #000;
            }
        """)

    def refresh(self):
        self.z_panel.setText(str(self.parent.z_abs))
    
    def zChanged(self, text):
        self.parent.z_abs = float(text)
        try:
            if self.parent.plot.restframe:
                self.parent.plot.updateVelocityAxis()
            self.parent.abs.redraw()
        except:
            pass

    def openURL(self, typ):
        id = getIDfromName(self.parent.s[self.parent.s.ind].filename)
        print(id)
        if typ == 'SAS':
            url = QUrl('https://dr14.sdss.org/spectrumDetail?mjd={0:d}&fiber={1:d}&plateid={2:d}'.format(id[1],id[2],id[0]))
        elif typ == 'SkyS':
            url = QUrl('http://skyserver.sdss.org/dr14/en/tools/explore/Summary.aspx?plate={0:d}&fiber={1:d}&mjd={2:d}'.format(id[0], id[2], id[1]))
        if not QDesktopServices.openUrl(url):
            QMessageBox.warning(self, 'Open Url', 'Could not open url')

class sviewer(QMainWindow):
    
    def __init__(self):
        super().__init__()

        #self.setWindowFlags(Qt.FramelessWindowHint)
        self.initStatus()
        self.initUI()
        self.initStyles()
        self.initData()

    def initStyles(self):
        self.setStyleSheet(open('config/styles.ini').read())

    def initStatus(self):
        self.t = Timer()
        self.setAcceptDrops(True)
        self.abs_H2_status = 0
        self.abs_DLA_status = 0
        self.abs_DLAmajor_status = 1
        self.abs_Molec_status = 0
        self.abs_SF_status = 1
        self.normview = False
        if platform.system() == 'Windows':
            self.config = 'config/options.ini'
        elif platform.system() == 'Linux':
            self.config = 'config/options_linux.ini'
        self.develope = self.options('developerMode', config=self.config)
        self.SDSSfolder = self.options('SDSSfolder', config=self.config)
        self.SDSSDR14 = self.options('SDSSDR14', config=self.config)
        if self.SDSSDR14 is not None and os.path.isfile(self.SDSSDR14):
            self.SDSSDR14 = h5py.File(self.SDSSDR14, 'r')
        self.SDSSLeefolder = self.options('SDSSLeefolder', config=self.config)
        self.SDSSdata = []
        self.SDSS_filters_status = 0
        self.sdss_filters = None
        self.UVESSetup_status = False
        self.XQ100folder = self.options('XQ100folder', config=self.config)
        self.P94folder = self.options('P94folder', config=self.config)
        self.work_folder = self.options('work_folder', config=self.config)
        self.plot_set_folder = self.options('plot_set_folder', config=self.config)
        self.VandelsFile = self.options('VandelsFile', config=self.config)
        self.KodiaqFile = self.options('KodiaqFile', config=self.config)
        self.UVESfolder = self.options('UVESfolder', config=self.config)
        self.IGMspecfile = self.options('IGMspecfile', config=self.config)
        self.z_abs = 0
        self.lines = lineList(self)
        self.line_reper = line('HI', 1215.6701, 0.4164, 6.265e8, ref='???')
        self.regions = []
        self.show_residuals = self.options('show_residuals')
        self.show_2d = self.options('show_2d')
        self.save_opt = ['cont', 'points', 'fit', 'others', 'fit_results']
        self.export_opt = ['cont', 'fit']
        self.export2d_opt = ['spectrum', 'err', 'mask', 'cr', 'sky', 'trace']
        self.num_between = int(self.options('num_between'))
        self.tau_limit = float(self.options('tau_limit'))
        self.comp_view = self.options('comp_view')
        self.animateFit = self.options('animateFit')
        self.polyDeg = int(self.options('polyDeg'))
        self.SDSScat = self.options('SDSScat')
        self.comp = 0
        self.fitprocess = None
        self.fitModel = None
        self.chooseFit = None
        self.preferences = None
        self.exp = None
        self.fitResults = None
        self.fitres = None
        self.MCMC = None
        self.extract2dwindow = None
        self.fitContWindow = None
        self.rescale_ind = 0

    def initUI(self):
        
        dbg = pg.dbg()
        # self.specview sets the type of plot representation
        for l in ['specview', 'selectview', 'linelabels', 'showinactive', 'show_osc', 'fitType', 'fitComp', 'fitPoints']:
            setattr(self, l, self.options(l))
        # >>> create panel for plotting spectra
        self.plot = plotSpectrum(self)
        self.vb = self.plot.getPlotItem().getViewBox()
        self.s = Speclist(self)
        #self.plot.setFrameShape(QFrame.StyledPanel)
        
        self.panel = buttonpanel(self)
        self.panel.setFrameShape(QFrame.StyledPanel)

        self.splitter = QSplitter(Qt.Vertical)
        self.splitter_plot = QSplitter(Qt.Vertical)
        self.splitter_plot.addWidget(self.plot)
        self.splitter_fit = QSplitter(Qt.Horizontal)
        self.splitter_fit.addWidget(self.splitter_plot)
        self.splitter.addWidget(self.splitter_fit)

        splitter_2 = QSplitter(Qt.Horizontal)
        splitter_2.addWidget(self.panel)
        self.console = Console(self)
        splitter_2.addWidget(self.console)
        splitter_2.setSizes([500, 500])
        self.splitter.addWidget(splitter_2)
        self.splitter.setSizes([1900, 100])

        self.setCentralWidget(self.splitter)
        
        # >>> create Menu
        self.initMenu()
        
        # create toolbar
        #self.toolbar = self.addToolBar('B-spline')
        #self.toolbar.addAction(Bspline)
        
        # >>> create status bar
        self.statusBarWidget = QStatusBar()
        self.setStatusBar(self.statusBarWidget)
        self.statusBar = QLabel()
        self.statusBar.setFixedSize(600, 30)
        self.statusBarWidget.addWidget(self.statusBar)
        self.chiSquare = QLabel('')
        self.chiSquare.setFixedSize(300, 30)
        self.statusBarWidget.addWidget(self.chiSquare)
        self.MCMCprogress = QLabel('')
        self.MCMCprogress.setFixedSize(400, 30)
        self.statusBarWidget.addWidget(self.MCMCprogress)
        self.statusBar.setText('Ready')

        self.draw()
        self.showMaximized()
        self.show()
         
    def initMenu(self):
        
        menubar = self.menuBar()
        fileMenu = menubar.addMenu('&File')
        viewMenu = menubar.addMenu('&View')
        linesMenu = menubar.addMenu('&Lines')
        fitMenu = menubar.addMenu('&Fit')
        spec1dMenu = menubar.addMenu('&1d spec')
        spec2dMenu = menubar.addMenu('&2d spec')
        combineMenu = menubar.addMenu('&Combine')
        SDSSMenu = menubar.addMenu('&SDSS')
        samplesMenu = menubar.addMenu('&Samples')
        generateMenu = menubar.addMenu('&Generate')
        obsMenu = menubar.addMenu('&Observations')
        helpMenu = menubar.addMenu('&Help')
        
        # >>> create File Menu items
        openAction = QAction('&Open...', self)
        openAction.setShortcut('Ctrl+O')
        openAction.setStatusTip('Open file')
        openAction.triggered.connect(self.showOpenDialog)
        
        saveAction = QAction('&Save', self)
        saveAction.setShortcut('Ctrl+S')
        saveAction.setStatusTip('Save file')
        saveAction.triggered.connect(self.saveFilePressed)

        saveAsAction = QAction('&Save as...', self)
        saveAsAction.setStatusTip('Save file as')
        saveAsAction.triggered.connect(self.showSaveDialog)

        importAction = QAction('&Import spectrum...', self)
        importAction.setShortcut('Ctrl+I')
        importAction.setStatusTip('Import spectrum')
        importAction.triggered.connect(self.showImportDialog)

        import2dAction = QAction('&Import 2d spectrum...', self)
        import2dAction.setStatusTip('Import 2d spectrum')
        import2dAction.triggered.connect(self.show2dImportDialog)

        exportAction = QAction('&Export spectrum...', self)
        exportAction.setStatusTip('Export spectrum')
        exportAction.triggered.connect(self.showExportDialog)

        export2dAction = QAction('&Export 2d spectrum...', self)
        export2dAction.setStatusTip('Export 2d spectrum')
        export2dAction.triggered.connect(self.show2dExportDialog)

        exportDataAction = QAction('&Export data...', self)
        exportDataAction.setStatusTip('Export data')
        exportDataAction.triggered.connect(self.showExportDataDialog)
        
        importList = QAction('&Import List...', self)
        importList.setStatusTip('Import list of spectra')
        importList.triggered.connect(self.showImportListDialog)

        importFolder = QAction('&Import Folder...', self)
        importFolder.setStatusTip('Import list of spectra from folder')
        importFolder.triggered.connect(self.showImportFolderDialog)

        exitAction = QAction('&Exit', self)
        #exitAction.setShortcut('Ctrl+Q')
        exitAction.setStatusTip('Exit application')
        exitAction.triggered.connect(qApp.quit)
        
        fileMenu.addAction(openAction)
        fileMenu.addAction(saveAction)
        fileMenu.addAction(saveAsAction)
        fileMenu.addSeparator()
        fileMenu.addAction(importAction)
        fileMenu.addAction(import2dAction)
        fileMenu.addAction(importList)
        fileMenu.addAction(importFolder)
        fileMenu.addSeparator()
        fileMenu.addAction(exportAction)
        fileMenu.addAction(export2dAction)
        fileMenu.addAction(exportDataAction)
        fileMenu.addSeparator()
        fileMenu.addAction(exitAction)
        
        # >>> create View Menu items

        exp = QAction('&Exposures', self)
        exp.setShortcut('F2')
        exp.setStatusTip('Show list of exposures')
        exp.triggered.connect(self.showExpList)

        self.showResiduals = QAction('&Residuals', self)
        self.showResiduals.setShortcut('F4')
        self.showResiduals.setStatusTip('Show/Hide Residuals panel')
        self.showResiduals.triggered.connect(partial(self.showResidualsPanel, show=None))
        self.showResidualsPanel(self.show_residuals)

        self.show2d = QAction('&2d spectrum', self)
        self.show2d.setShortcut('F9')
        self.show2d.setStatusTip('Show/Hide 2d spectrum panel')
        self.show2d.triggered.connect(partial(self.show2dPanel, show=None))
        self.show2dPanel(self.show_2d)

        preferences = QAction('&Preferences...', self)
        preferences.setStatusTip('Show preferences')
        preferences.setShortcut('F11')
        preferences.triggered.connect(self.showPreferences)

        showLines = QAction('&Plot lines', self)
        showLines.setShortcut('Ctrl+L')
        showLines.setStatusTip('Plot lines using matplotlib')
        showLines.triggered.connect(partial(self.showLines, True))

        snapShot = QAction('&Plot snapshot', self)
        snapShot.setStatusTip('Snapshop of view using matplotlib')
        snapShot.triggered.connect(self.takeSnapShot)

        viewMenu.addAction(exp)
        viewMenu.addAction(self.showResiduals)
        viewMenu.addAction(self.show2d)
        viewMenu.addAction(preferences)
        viewMenu.addSeparator()
        viewMenu.addAction(showLines)
        viewMenu.addAction(snapShot)

        # >>> create Line Menu items
        self.linesH2 = QAction('&H2 lines', self, checkable=True)
        self.linesH2.setStatusTip('Add H2 lines')
        self.linesH2.triggered.connect(partial(self.absLines, 'abs_H2_status'))
        self.linesH2.setChecked(self.abs_H2_status)

        self.linesDLA = QAction('&DLA', self, checkable=True)
        self.linesDLA.setStatusTip('Add extended list of DLA lines')
        self.linesDLA.triggered.connect(partial(self.absLines, 'abs_DLA_status'))
        self.linesDLA.setChecked(self.abs_DLA_status)

        self.linesDLAmajor = QAction('&DLA only major', self, checkable=True)
        self.linesDLAmajor.setStatusTip('Add list of major DLA lines')
        self.linesDLAmajor.triggered.connect(partial(self.absLines, 'abs_DLAmajor_status'))
        self.linesDLAmajor.setChecked(self.abs_DLAmajor_status)

        self.linesMolec = QAction('&Minor molecules', self, checkable=True)
        self.linesMolec.setStatusTip('Add various molecular lines')
        self.linesMolec.triggered.connect(partial(self.absLines, 'abs_Molec_status'))
        self.linesMolec.setChecked(self.abs_Molec_status)

        self.linesSF = QAction('&Emission lines', self, checkable=True)
        self.linesSF.setStatusTip('Star-formation emission lines')
        self.linesSF.triggered.connect(partial(self.absLines, 'abs_SF_status'))
        self.linesSF.setChecked(self.abs_SF_status)

        linesChoice = QAction('&Choose lines', self)
        linesChoice.setStatusTip('Choose lines to indicate')
        linesChoice.triggered.connect(self.absChoicelines)

        hideAll = QAction('&Hide all', self)
        hideAll.setStatusTip('Remove all line indicators')
        hideAll.triggered.connect(self.hideAllLines)

        linesMenu.addAction(self.linesDLA)
        linesMenu.addAction(self.linesDLAmajor)
        linesMenu.addAction(self.linesH2)
        linesMenu.addAction(self.linesMolec)
        linesMenu.addAction(self.linesSF)
        linesMenu.addSeparator()
        linesMenu.addAction(linesChoice)
        linesMenu.addAction(hideAll)

        # >>> create Fit Menu items
        
        setFit = QAction('&Fit model', self)
        setFit.setShortcut('Ctrl+F')
        setFit.setStatusTip('set Fit model parameters')
        setFit.triggered.connect(self.setFitModel)

        chooseFitPars = QAction('&Fit parameters', self)
        chooseFitPars.setStatusTip('Choose particular fit parameters')
        chooseFitPars.setShortcut('F3')
        chooseFitPars.triggered.connect(self.chooseFitPars)

        showFit = QAction('&Show fit', self)
        showFit.setStatusTip('Show fit only near fitted points')
        showFit.setShortcut('F')
        showFit.triggered.connect(partial(self.showFit, -1, False))

        showFullFit = QAction('&Show full fit', self)
        showFullFit.setStatusTip('Show fit in all avaliable lines')
        showFullFit.setShortcut('Shift+F')
        showFullFit.triggered.connect(partial(self.showFit, -1, True))

        fitLM = QAction('&Fit LM', self)        
        fitLM.setStatusTip('Fit by Levenberg-Marquadt method')
        fitLM.triggered.connect(self.fitLM)

        fitMCMC = QAction('&Fit MCMC...', self)
        fitMCMC.setStatusTip('Fit by MCMC method')
        fitMCMC.setShortcut('Ctrl+M')
        fitMCMC.triggered.connect(self.fitMCMC)

        fitGrid = QAction('&Grid fit', self)
        fitGrid.setStatusTip('Brute force calculation on the grid of parameters')
        fitGrid.triggered.connect(partial(self.fitGrid, num=None))

        stopFit = QAction('&Stop Fit', self)
        stopFit.setStatusTip('Stop fitting process')
        stopFit.triggered.connect(self.stopFit)

        fitResults = QAction('&Fit results', self)
        fitResults.setStatusTip('Show fit results')
        fitResults.setShortcut('F8')
        fitResults.triggered.connect(self.showFitResults)

        fitCheb = QAction('&Fit Cheb', self)
        fitCheb.setStatusTip('Adjust continuum by Chebyshev polynomials')
        fitCheb.triggered.connect(partial(self.fitCheb, typ='cheb'))

        fitExt = QAction('&Fit Extinction...', self)
        fitExt.setStatusTip('Fit extinction')
        fitExt.triggered.connect(self.fitExt)

        fitGauss = QAction('&Fit by gaussian line', self)
        fitGauss.setStatusTip('Fit gauss')
        fitGauss.triggered.connect(self.fitGauss)

        fitPower = QAction('&Power law fit', self)
        fitPower.setStatusTip('Fit by power law function')
        fitPower.triggered.connect(self.fitPowerLaw)

        fitPoly = QAction('&Polynomial fit', self)
        fitPoly.setStatusTip('Fit by polynomial function')
        fitPoly.triggered.connect(partial(self.fitPoly, None))

        fitMinEnvelope = QAction('&Envelope fit', self)
        fitMinEnvelope.setStatusTip('Find bottom envelope')
        fitMinEnvelope.triggered.connect(partial(self.fitMinEnvelope, res=200))

        AncMenu = QMenu('&Diagnostic plots', self)
        AncMenu.setStatusTip('Some ancillary for fit procedures')

        H2Exc = QAction('&H2 exc. diagram', self)
        H2Exc.setStatusTip('Show H2 excitation diagram')
        H2Exc.triggered.connect(self.H2ExcDiag)

        H2ExcTemp = QAction('&H2 Excitation temperature', self)
        H2ExcTemp.setStatusTip('Calculate H2 excitation temperature')
        H2ExcTemp.triggered.connect(partial(self.H2ExcitationTemp, levels=[0, 1, 2], ind=None, plot=True))

        MetalAbundance = QAction('&Metal abundance', self)
        MetalAbundance.setStatusTip('Show Metal abundances')
        MetalAbundance.triggered.connect(self.showMetalAbundance)

        fitMenu.addAction(setFit)
        fitMenu.addAction(chooseFitPars)
        fitMenu.addAction(showFit)
        fitMenu.addAction(showFullFit)
        fitMenu.addSeparator()
        fitMenu.addAction(fitLM)
        fitMenu.addAction(fitMCMC)
        fitMenu.addAction(fitGrid)
        fitMenu.addAction(stopFit)
        fitMenu.addAction(fitResults)
        fitMenu.addSeparator()
        fitMenu.addAction(fitCheb)
        fitMenu.addAction(fitExt)
        fitMenu.addAction(fitGauss)
        fitMenu.addAction(fitPower)
        fitMenu.addAction(fitPoly)
        fitMenu.addAction(fitMinEnvelope)
        fitMenu.addSeparator()
        fitMenu.addMenu(AncMenu)
        AncMenu.addAction(H2Exc)
        AncMenu.addAction(H2ExcTemp)
        AncMenu.addAction(MetalAbundance)

        # >>> create 1d spec Menu items

        fitCont = QAction('&Continuum...', self)
        fitCont.setStatusTip('Construct continuum using various methods')
        fitCont.setShortcut('Ctrl+C')
        fitCont.triggered.connect(partial(self.fitCont))

        rescaleErrs = QAction('&Adjust errors', self)
        rescaleErrs.setStatusTip('Adjust uncertainties to dispersion in the spectrum')
        rescaleErrs.triggered.connect(partial(self.rescale))

        spec1dMenu.addAction(fitCont)
        spec1dMenu.addAction(rescaleErrs)

        # >>> create 2d spec Menu items
        # >>> create 2d spec Menu items

        extract = QAction('&Extract', self)
        extract.setStatusTip('extract 1d spectrum from 2d spectrum')
        extract.setShortcut('Ctrl+D')
        extract.triggered.connect(self.extract2d)

        spec2dMenu.addAction(extract)

        # >>> create Combine Menu items
        
        expList = QAction('&Exposure list', self)
        expList.setStatusTip('show Exposure list')
        expList.triggered.connect(self.showExpListCombine)
                
        selectCosmics = QAction('&Select cosmic', self)        
        selectCosmicsUVESSet = QAction('&Load Settings', self)
        selectCosmics.triggered.connect(self.selectCosmics)
        
        calcSmooth = QAction('&Smooth', self)        
        calcSmooth.setStatusTip('Smooth exposures')
        calcSmooth.triggered.connect(self.calcSmooth)
        
        coscaleExp = QAction('&Coscale', self)
        coscaleExp.setStatusTip('Coscale exposures')
        coscaleExp.triggered.connect(self.coscaleExposures)

        shiftExp = QAction('&Shift', self)
        shiftExp.setStatusTip('Shift exposure')
        shiftExp.triggered.connect(self.shiftExposure)

        rescaleExp = QAction('&Rescale', self)
        rescaleExp.setStatusTip('Rescale exposure')
        rescaleExp.triggered.connect(self.rescaleExposure)

        rescaleErrs = QAction('&Rescale errs', self)
        rescaleErrs.setStatusTip('Rescale uncertainties')
        rescaleErrs.triggered.connect(self.rescaleErrs)

        combine = QAction('&Combine...', self)
        combine.setStatusTip('Combine exposures')
        combine.triggered.connect(self.combine)

        rebin = QAction('&Rebin...', self)
        rebin.setStatusTip('Rebin exposures')
        rebin.triggered.connect(self.rebin)
        
        combineMenu.addAction(expList)
        combineMenu.addSeparator()
        combineMenu.addAction(selectCosmics)
        combineMenu.addAction(calcSmooth)
        combineMenu.addAction(coscaleExp)
        combineMenu.addAction(shiftExp)
        combineMenu.addAction(rescaleExp)
        combineMenu.addAction(rescaleErrs)
        combineMenu.addSeparator()
        combineMenu.addAction(combine)
        combineMenu.addAction(rebin)

        if self.develope:
            # >>> create SDSS Menu items
            loadSDSS = QAction('&load SDSS', self)
            loadSDSS.setStatusTip('Load SDSS by Plate/fiber')
            loadSDSS.triggered.connect(self.showSDSSdialog)

            SDSSLeelist = QAction('&DR9 Lee list', self)
            SDSSLeelist.setStatusTip('load SDSS DR9 Lee database')
            SDSSLeelist.triggered.connect(self.loadSDSSLee)

            SDSSlist = QAction('&SDSS list', self)
            SDSSlist.setStatusTip('SDSS list')
            SDSSlist.triggered.connect(self.show_SDSS_list)

            SDSSSearchH2 = QAction('&Search H2', self)
            SDSSSearchH2.setStatusTip('Search H2 absorption systems')
            SDSSSearchH2.triggered.connect(self.search_H2)

            SDSSH2cand = QAction('&Show H2 cand.', self)
            SDSSH2cand.setStatusTip('Show H2 cand.')
            SDSSH2cand.triggered.connect(self.show_H2_cand)

            SDSSStack = QAction('&Stack', self)
            SDSSStack.setStatusTip('Calculate SDSS Stack spectrum')
            SDSSStack.triggered.connect(self.calc_SDSS_Stack_Lee)

            SDSSDLA = QAction('&DLA search', self)
            SDSSDLA.setStatusTip('Search for DLA systems')
            SDSSDLA.triggered.connect(self.calc_SDSS_DLA)

            SDSSfilters = QAction('&SDSS filters', self, checkable=True)
            SDSSfilters.setStatusTip('Add SDSS filters magnitudes')
            SDSSfilters.triggered.connect(self.show_SDSS_filters)
            SDSSfilters.setChecked(self.SDSS_filters_status)

            SDSSPhot = QAction('&SDSS photometry', self)
            SDSSPhot.setStatusTip('Show SDSS photometry window')
            SDSSPhot.triggered.connect(self.SDSSPhot)

            SDSSMenu.addAction(loadSDSS)
            SDSSMenu.addSeparator()
            SDSSMenu.addAction(SDSSLeelist)
            SDSSMenu.addAction(SDSSlist)
            SDSSMenu.addSeparator()
            SDSSMenu.addAction(SDSSSearchH2)
            SDSSMenu.addAction(SDSSH2cand)
            SDSSMenu.addSeparator()
            SDSSMenu.addAction(SDSSStack)
            SDSSMenu.addAction(SDSSDLA)
            SDSSMenu.addSeparator()
            SDSSMenu.addAction(SDSSfilters)
            SDSSMenu.addAction(SDSSPhot)
        
            # >>> create Samples Menu items
            XQ100list = QAction('&XQ100 list', self)
            XQ100list.setStatusTip('load XQ100 list')
            XQ100list.triggered.connect(self.showXQ100list)

            P94list = QAction('&P94 list', self)
            P94list.setStatusTip('load P94 list')
            P94list.triggered.connect(self.showP94list)

            DLAlist = QAction('&DLA list', self)
            DLAlist.setStatusTip('load DLA list')
            DLAlist.triggered.connect(self.showDLAlist)

            LyaforestMenu = QMenu('&Lyaforest', self)

            Lyalist = QAction('&Lyaforest sample', self)
            Lyalist.setStatusTip('load lya forest sample')
            Lyalist.triggered.connect(self.showLyalist)
            LyaforestMenu.addAction(Lyalist)

            Lyalines = QAction('&Lyaforest line', self)
            Lyalines.setStatusTip('load lya forest lines')
            Lyalines.triggered.connect(self.showLyalines)
            LyaforestMenu.addAction(Lyalines)

            Vandels = None
            if self.VandelsFile is not None and os.path.isfile(self.VandelsFile):
                Vandels = QAction('&Vandels', self)
                Vandels.setStatusTip('load Vandels catalog')
                Vandels.triggered.connect(self.showVandels)

            Kodiaq = None
            if self.KodiaqFile is not None and os.path.isfile(self.KodiaqFile):
                Kodiaq = QAction('&KODIAQ DR2', self)
                Kodiaq.setStatusTip('load Kodiaq DR2 catalog')
                Kodiaq.triggered.connect(self.showKodiaq)

            UVES = None
            if self.UVESfolder is not None and os.path.isdir(self.UVESfolder):
                UVES = QAction('&UVES ADP QSO', self)
                UVES.setStatusTip('load QSO sample from UVES ADP')
                UVES.triggered.connect(self.showUVES)

            IGMspecMenu = None
            if self.IGMspecfile is not None and os.path.isfile(self.IGMspecfile):
                IGMspecMenu = QMenu('&IGMspec', self)
                IGMspecMenu.setStatusTip('Data from IGMspec database')
                try:
                    self.IGMspec = h5py.File(self.IGMspecfile, 'r')
                    for i in self.IGMspec.keys():
                        item = QAction('&'+i, self)
                        item.triggered.connect(partial(self.showIGMspec, i, None))
                        IGMspecMenu.addAction(item)
                except:
                    pass

            samplesMenu.addAction(XQ100list)
            samplesMenu.addAction(P94list)
            samplesMenu.addAction(DLAlist)
            samplesMenu.addMenu(LyaforestMenu)
            if Vandels is not None:
                samplesMenu.addAction(Vandels)
            if Kodiaq is not None:
                samplesMenu.addAction(Kodiaq)
            if UVES is not None:
                samplesMenu.addAction(UVES)
            samplesMenu.addSeparator()
            if IGMspecMenu is not None:
                samplesMenu.addMenu(IGMspecMenu)

        # >>> create Generate Menu items
        loadSDSSmedian = QAction('&load VanDen Berk', self)        
        loadSDSSmedian.setStatusTip('load median spectrum from SDSS (VanDen Berk et al. 2001)')
        loadSDSSmedian.triggered.connect(self.loadSDSSmedian)
        
        loadHSTmedian = QAction('&load HST', self)        
        loadHSTmedian.setStatusTip('load median spectrum from HST 2001')
        loadHSTmedian.triggered.connect(self.loadHSTmedian)
        
        addAbsSystem = QAction('&add system', self)        
        addAbsSystem.setStatusTip('add absorption system')
        addAbsSystem.triggered.connect(self.add_abs_system)
        
        addDustSystem = QAction('&add dust', self)        
        addDustSystem.setStatusTip('add dust')
        addDustSystem.triggered.connect(self.add_dust_system)

        colorColorPlot = QAction('&color-color', self)
        colorColorPlot.setStatusTip('show color-color plot')
        colorColorPlot.triggered.connect(self.colorColorPlot)

        generateMenu.addAction(loadSDSSmedian)
        generateMenu.addAction(loadHSTmedian)
        generateMenu.addSeparator()
        generateMenu.addAction(addAbsSystem)
        generateMenu.addAction(addDustSystem)
        generateMenu.addSeparator()
        generateMenu.addAction(colorColorPlot)

        # >>> create Obervations Menu items
        UVESMenu = QMenu('&UVES', self)
        UVESMenu.setStatusTip('methods for UVES/VLT')

        self.UVESSetup = QAction('&Setup', self, checkable=True)
        self.UVESSetup.setStatusTip('&Choose appropriate Setup')
        self.UVESSetup.triggered.connect(self.chooseUVESSetup)
        self.UVESSetup.setChecked(self.UVESSetup_status)

        UVESetc = QAction('&load ETC data', self)
        UVESetc.setStatusTip('Add data from UVES ETC')
        UVESetc.triggered.connect(self.addUVESetc)

        UVESMenu.addAction(self.UVESSetup)
        UVESMenu.addAction(UVESetc)
        obsMenu.addMenu(UVESMenu)

        observability = QAction('&Observability', self)
        observability.setStatusTip('&Calculate observability for given targets')
        observability.triggered.connect(self.observability)

        obsMenu.addSeparator()
        obsMenu.addAction(observability)

        # >>> create Help Menu items
        howto = QAction('&How to ...', self)
        howto.setShortcut('F1')
        howto.setStatusTip('How to do')
        howto.triggered.connect(self.info_howto)
        
        tutorial = QAction('&Tutorial', self)        
        tutorial.setStatusTip('Some tutorial')
        tutorial.triggered.connect(self.info_tutorial)
        
        about = QAction('&About', self)
        about.setStatusTip('About the program')
        about.triggered.connect(self.info_about)
        
        helpMenu.addAction(howto)
        helpMenu.addAction(tutorial)
        helpMenu.addSeparator()
        helpMenu.addAction(about)

    def initData(self):
        self.fit = fitPars(self)
        #self.atomic = atomic_data()
        self.atomic = atomicData()
        self.atomic.readdatabase()
        self.abs = absSystemIndicator(self)
        for s in ['H2', 'DLAmajor', 'DLA', 'Molec', 'SF']:
            self.absLines('abs_'+s+'_status', value=getattr(self, 'abs_'+s+'_status'))

        filename = self.options('loadfile', config=self.config)
        if os.path.exists(filename):
            import importlib.util
            spec = importlib.util.spec_from_file_location("load", filename)
            foo = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(foo)
            foo.loadaction(self)

    def options(self, opt, value=None, config='config/options.ini'):
        """
        Read and write options from the config file
        """
        with open(config) as f:
            s = f.readlines()

        for i, line in enumerate(s):
            if len(line.split()) > 0 and opt == line.split()[0] and not any([line.startswith(st) for st in ['#', '!', '$', '%']]):
                if value is None:
                    if len(line.split()) > 2:
                        if line.split()[2] == 'None':
                            return None
                        elif line.split()[2] == 'True':
                            return True
                        elif line.split()[2] == 'False':
                            return False
                        else:
                            return ' '.join(line.split()[2:])
                    else:
                        return ''
                else:
                    setattr(self, opt, value)
                    s[i] = "{0:20}  :  {1:} \n".format(opt, value)
                break
        else:
            return None
            #return 'option {0} was not found'.format(opt)

        with open('config/options.ini', 'w') as f:
            for line in s:
                f.write(line)

    #>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    #>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    #>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    # >>>
    # >>>   GUI routines
    # >>>
    #>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    #>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    #>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls:
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls:
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        if event.mimeData().hasUrls:
            event.setDropAction(Qt.CopyAction)
            event.accept()
            # Workaround for OSx dragging and dropping

            filelist = []
            for url in event.mimeData().urls():
                filelist.append(str(url.toLocalFile()))
                print('drop:', str(url.toLocalFile()))
                if str(url.toLocalFile()).endswith('.spv'):
                    self.openFile(str(url.toLocalFile()))
                else:
                    self.importSpectrum(filelist, append=True)
        else:
            event.ignore()

    def mousePressEvent(self, event):
        #if self.b_status:
        pass
        
    def mouseMoveEvent(self, event):
        pass
    
    def draw(self):
        # >>> add zero line level
        self.zeroline = pg.InfiniteLine(0.0, 0, pen=pg.mkPen(color=(148, 103, 189), width=1, style=Qt.DashLine))
        if 0:
            self.zeroline.setMovable(1)
            self.zeroline.setHoverPen(color=(214, 39, 40), width=3)
        self.vb.addItem(self.zeroline)

    def absLines(self, status='', sig=True, value=None, verbose=False):

        if verbose:
            print(status, value)

        if value is not None:
            setattr(self, status, value)
        else:
            setattr(self, status, 1 - getattr(self, status))
        if value is not 0:
            if status == 'abs_H2_status' and value is not 0:
                lines, color, va = self.atomic.list(['H2j'+str(i) for i in range(3)]), (229, 43, 80), 'down'
            if status == 'abs_DLA_status' and value is not 0:
                lines, color, va = self.atomic.DLA_list(), (105, 213, 105), 'down'
            if status == 'abs_DLAmajor_status' and value is not 0:
                lines, color, va = self.atomic.DLA_major_list(), (105, 213, 105), 'down'
            if status == 'abs_Molec_status' and value is not 0:
                lines, color, va = self.atomic.Molecular_list(), (255, 111, 63), 'down'
            if status == 'abs_SF_status' and value is not 0:
                lines, color, va = self.atomic.EmissionSF_list(), (0, 204, 255), 'up'

            if verbose:
                print('linelist:', lines)

            if getattr(self, status):
                self.abs.add(lines, color=color, va=va)
            else:
                self.abs.remove(lines)

    def absChoicelines(self):
        d = {'H2': ['J='+str(i) for i in range(10)]}
        d = {k: [] for k in self.atomic.keys()}
        self.choiceLinesWindow = choiceLinesWidget(self, d)
        self.choiceLinesWindow.show()

    def hideAllLines(self):
        self.console.exec_command('hide all')
        for s in ['H2', 'DLA', 'DLAmajor', 'Molec']:
            getattr(self, 'lines'+s).setChecked(False)
            setattr(self, 'abs_' + s + '_status', False)

    def setz_abs(self, text):
        self.z_abs = float(text)
        self.panel.z_panel.setText(str(self.z_abs))
        if self.plot.restframe:
            self.plot.updateVelocityAxis()
        self.abs.redraw()

    #>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    #>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    #>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    # >>>
    # >>>   File menu routines
    # >>>
    #>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    #>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    #>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    
    def showOpenDialog(self):
        fname = QFileDialog.getOpenFileName(self, 'Open file', self.work_folder)
        
        if fname[0]:

            self.openFile(fname[0])
            self.statusBar.setText('Data was read from ' + fname[0])
            self.showFit()


    def openFile(self, filename, zoom=True, skip_header=0, remove_regions=False, remove_doublets=False):

        if remove_regions:
            for r in reversed(self.plot.regions[:]):
                self.plot.regions.remove(r)
            self.plot.regions = regionList(self.plot)

        if remove_doublets:
            for d in reversed(self.plot.doublets[:]):
                d.remove()
            self.plot.doublets = doubletList(self.plot)

        folder = os.path.dirname(filename)

        with open(filename) as f:
            d = f.readlines()

        i = -1 + skip_header
        while (i < len(d)-1):
            i += 1
            if '%' in d[i] or any([x in d[i] for x in ['spect', 'Bcont', 'fitting']]):
                if '%' in d[i]:
                    specname = d[i][1:].strip()
                    try:
                        ind = [s.filename for s in self.s].index(specname)
                    except:
                        ind = -1
                        try:
                            if all([slash not in specname for slash in ['/', '\\']]):
                                specname = folder + '/' + specname

                            if not self.importSpectrum(specname, append=True):
                                st = re.findall(r'spec-\d{4}-\d{5}-\d+', specname)
                                if len(st) > 0:
                                    self.loadSDSS(plate=st[0].split('-')[1], fiber=st[0].split('-')[3])
                            ind = len(self.s) - 1
                        except:
                            pass
                    i += 1
                else:
                    ind = 0

                if i > len(d) - 1:
                    break

                if ind == -1 and 'spectrum' in d[i]:
                    n = int(d[i].split()[1])
                    if n > 0:
                        x, y, err = [], [], []
                        if n > 0:
                            for t in range(n):
                                i += 1
                                w = d[i].split()
                                x.append(float(w[0]))
                                y.append(float(w[1]))
                                if len(w) > 2:
                                    err.append(float(w[2]))
                        self.importSpectrum(specname, spec=[np.asarray(x), np.asarray(y), np.asarray(err)], append=True)
                        ind = len(self.s) - 1

                if ind > -1:
                    while all([x not in d[i] for x in ['%', '----', 'doublet', 'region', 'fit_model']]):
                        if 'Bcont' in d[i]:
                            self.s[ind].spline = gline()
                            n = int(d[i].split()[1])
                            if n > 0:
                                for t in range(n):
                                    i += 1
                                    w = d[i].split()
                                    self.s[ind].spline.add(float(w[0]), float(w[1]))
                                self.s[ind].calc_spline()

                        if 'fitting_points' in d[i]:
                            self.s[ind].mask.set(x=np.zeros_like(self.s[ind].spec.x(), dtype=bool))
                            n = int(d[i].split()[1])
                            if n > 0:
                                i += 1
                                w = [float(line.split()[0]) for line in d[i:i+n]]
                                self.s[ind].add_exact_points(w, redraw=False)
                                i += n-1
                                self.s[ind].mask.normalize()

                        if 'bad_pixels' in d[i]:
                            self.s[ind].bad_mask.set(x=np.zeros_like(self.s[ind].spec.x(), dtype=bool))
                            n = int(d[i].split()[1])
                            if n > 0:
                                i += 1
                                w = [float(line.split()[0]) for line in d[i:i + n]]
                                self.s[ind].add_exact_points(w, redraw=False, bad=True)
                                i += n - 1
                                self.s[ind].bad_mask.normalize()

                        if 'resolution' in d[i]:
                            self.s[ind].resolution = int(float(d[i].split()[1]))

                        i += 1

                        if i > len(d) - 1:
                            break

            if '%' in d[i]:
                i -= 1

            if 'regions' in d[i]:
                ns = int(d[i].split()[1])
                for r in range(ns):
                    self.plot.regions.add('..'.join(d[i+1+r].split()))

            if 'doublets' in d[i]:
                ns = int(d[i].split()[1])
                for r in range(ns):
                    i += 1
                    print(d[i].split()[0], float(d[i].split()[1]))
                    self.plot.doublets.append(Doublet(self.plot, name=d[i].split()[0], z=float(d[i].split()[1])))

            if 'lines' in d[i]:
                self.lines = lineList(self)
                ns = int(d[i].split()[1])
                for r in range(ns):
                    i += 1
                    self.lines.add(d[i].strip())

            if 'fit_model' in d[i]:
                self.plot.remove_pcRegion()
                self.fit = fitPars(self)
                num = int(d[i].split()[1])
                for k in range(num):
                    i += 1
                    self.fit.readPars(d[i])
                if num > 0:
                    self.setz_abs(self.fit.sys[0].z.val)
                self.fit.showLines()

            if 'fit_results' in d[i]:
                num = int(d[i].split()[1])
                for k in range(num):
                    i += 1
                    self.fit.setValue(d[i].split()[0], d[i].split()[2], 'unc')

        if zoom:
            try:
                self.plot.set_range(self.s[self.s.ind].spline.x[0], self.s[self.s.ind].spline.x[-1])
            except:
                pass

        self.work_folder = os.path.dirname(filename)
        self.options('work_folder', self.work_folder)
        self.options('filename_saved', filename)
        self.s.redraw(self.s.ind)

    def saveFile(self, filename, save_name=True):
        if not filename.endswith('.spv'):
            filename += '.spv'

        with open(filename, 'w') as f:

            if any([opt in self.save_opt for opt in ['spectrum', 'cont', 'points']]):
                for s in self.s:
                    if save_name:
                        f.write('%{}\n'.format(s.filename))

                    # >>> save spectra
                    if 'spectrum' in self.save_opt:
                        num = len(s.spec.x())
                        if num > 0:
                            if self.normview:
                                f.write('norm_spectrum:  {}\n'.format(num))
                            else:
                                f.write('spectrum:  {}\n'.format(num))
                            for x, y, err in zip(s.spec.x(), s.spec.y(), s.spec.err()):
                                f.write('{0:10.4f}  {1:10.4f}  {2:10.4f} \n'.format(x, y, err))

                    # >>> save cont
                    if 'cont' in self.save_opt:
                        f.write('Bcont:  {}\n'.format(s.spline.n))
                        if s.spline.n > 0:
                            for x, y in zip(s.spline.x, s.spline.y):
                                f.write('{0:10.4f}  {1:10.4e} \n'.format(x, y))

                    # >>> save fitting points:
                    if 'points' in self.save_opt:
                        num = np.sum(s.mask.x())
                        f.write('fitting_points:   {}\n'.format(num))
                        if num > 0:
                            for x in s.spec.x()[s.mask.x()]:
                                f.write('{:.5f}\n'.format(x))

                    # >>> save bad points:
                    if 'points' in self.save_opt:
                        f.write('bad_pixels:   {}\n'.format(np.sum(s.bad_mask.x())))
                        if np.sum(s.bad_mask.x()) > 0:
                            for x in s.spec.x()[s.bad_mask.x()]:
                                f.write('{:.5f}\n'.format(x))

                    # >>> save resolution:
                    if 'others' in self.save_opt:
                        if s.resolution not in [0, None]:
                            f.write('resolution:   {}\n'.format(s.resolution))

                    f.write('-------------------------\n')

            # >>> save other parameters
            if 'others' in self.save_opt:
                if len(self.plot.regions) > 0:
                    f.write('regions:   ' + str(len(self.plot.regions)) + '\n')
                    for r in self.plot.regions:
                        mi, ma = r.getRegion()
                        f.write('{0:11.5f} {1:11.5f} \n'.format(mi, ma))

                if len(self.plot.doublets) > 0:
                    f.write('doublets:   ' + str(len(self.plot.doublets)) + '\n')
                    for d in self.plot.doublets:
                        f.write('{0:5s} {1:9.7f} \n'.format(d.name, d.z))

                if len(self.lines) > 0:
                    f.write('lines:   ' + str(len(self.lines)) + '\n')
                    for l in self.lines:
                        f.write('{0}\n'.format(l))

            # >>> save fit model:
            if 'fit' in self.save_opt:
                pars = self.fit.list()
                f.write('fit_model: {0:}\n'.format(len(pars)))
                for p in pars:
                    f.write(p.str() + '\n')

            # >>> save fit result:
            if 'fit_results' in self.save_opt:
                pars = self.fit.list_fit()
                if any([p.unc.minus > 0 and p.unc.plus > 0 for p in pars]):
                    f.write('fit_results: {0:}\n'.format(len(pars)))
                    for p in pars:
                        f.write(str(p) + ' = ' + p.fitres(latex=True, showname=True) + '\n')

        self.statusBar.setText('Data is saved to ' + filename)

    def saveFilePressed(self):
        if self.options('filename_saved') is None:
            self.showSaveDialog()
        else:
            self.saveFile(self.options('filename_saved'))

    def showSaveDialog(self):
        self.exportData = ExportDataWidget(self, 'save')

    def showImportDialog(self):

        fname = QFileDialog.getOpenFileName(self, 'Import spectrum', self.work_folder)

        if fname[0]:
            
            self.importSpectrum(fname[0])
            self.abs.redraw()
            self.statusBar.setText('Spectrum is imported from ' + fname[0])

    def show2dImportDialog(self):

        fname = QFileDialog.getOpenFileName(self, 'Import 2d spectrum', self.work_folder)

        if fname[0]:
            self.import2dSpectrum(fname[0])
            self.statusBar.setText('2d spectrum is imported from ' + fname[0])


    def importSpectrum(self, filelist, spec=None, header=0, dir_path='', scale_factor=1, append=False, corr=True):

        if not append:
            for s in self.s:
                s.remove()
            self.s = Speclist(self)

        if isinstance(filelist, str):
            filelist = [filelist]

        if self.normview:
            self.normalize()

        for line in filelist:
            filename = line.split()[0]
            print(filename)
            s = Spectrum(self, name=filename)

            if spec is None:

                if filename.endswith('tar.gz'):
                    tar = tarfile.open(filename, 'r:gz')
                    for m in tar.getmembers():
                        if m.name.endswith('.fits'):
                            filename = tar.extractfile(m)
                            hdulist = fits.open(filename)
                else:
                    hdulist = None
                    if ':' not in filename:
                        filename = dir_path+filename

                if 'IGMspec' in filename:
                    if self.IGMspecfile is not None:
                        s1 = filename.split('/')
                        data = self.IGMspec[s1[1]]
                        d = np.empty([len(data['meta']['IGM_ID'])], dtype=[('SPEC_FILE', np.str_, 100)])
                        d['SPEC_FILE'] = np.array([x[:] for x in data['meta']['SPEC_FILE']])
                        ind = [i for i, d in enumerate(d['SPEC_FILE']) if  s1[2] in d][0]
                        s.set_data([data['spec'][ind]['wave'], data['spec'][ind]['flux'], data['spec'][ind]['sig']])
                        if s1[1] == 'KODIAQ_DR1':
                            s.spec.raw.clean(min=-1, max=2)
                            s.set_data()
                        s.resolution = data['meta']['R'][ind]

                elif hdulist is not None or filename.endswith('.fits'):
                    if hdulist is None:
                        hdulist = fits.open(filename)
                    if 'INSTRUME' in hdulist[0].header:
                        try:
                            if 'XSHOOTER' in hdulist[0].header['INSTRUME']:
                                prihdr = hdulist[1].data
                                s.set_data([prihdr[0][0][:]*10, prihdr[0][1][:]*1e17, prihdr[0][2][:]*1e17])

                            if any([instr in hdulist[0].header['INSTRUME'] for instr in ['UVES', 'VIMOS']]):
                                prihdr = hdulist[1].data
                                l = prihdr[0][0][:]
                                coef = 1e17 if 'VIMOS' in hdulist[0].header['INSTRUME'] else 1
                                s.set_data([l, prihdr[0][1][:]*coef, prihdr[0][2][:]*coef])
                                if 'SPEC_RES' in hdulist[0].header:
                                    s.resolution = hdulist[0].header['SPEC_RES']
                                if 'DATE-OBS' in hdulist[0].header:
                                    s.date = hdulist[0].header['DATE-OBS']
                                print(s.resolution, s.date)


                            try:
                                if corr:
                                    s.helio_vel = hdulist[0].header['HIERARCH ESO QC VRAD HELICOR']
                                    s.apply_shift(s.helio_vel)
                                    s.airvac()
                                    s.spec.raw.interpolate()
                            except:
                                pass
                        except:
                            print('fits file was not loaded')
                            return False

                    elif 'TELESCOP' in hdulist[0].header:
                        try:
                            if 'SDSS' in hdulist[0].header['TELESCOP']:
                                data = hdulist[1].data
                                DR9 = 0
                                if DR9:
                                    res_st = int((data.field('LOGLAM')[0] - self.LeeResid[0][0])*10000)
                                    print('SDSS:', res_st)
                                    #mask = data.field('MASK_COMB')[i_min:i_max]
                                    l = 10**data.field('LOGLAM')
                                    fl = data.field('FLUX')
                                    cont = (data.field('CONT') * self.LeeResid[1][res_st:res_st+len(l)]) #/ data.field('DLA_CORR')
                                    sig = (data.field('IVAR'))**(-0.5) / data.field('NOISE_CORR')
                                else:
                                    l = 10**data.field('loglam')
                                    fl = data.field('flux')
                                    sig = (data.field('ivar'))**(-0.5)
                                    cont = data.field('model')
                                s.set_data([l, fl, sig])
                                s.cont.set_data(l, cont)
                                s.resolution = 2000
                        except:
                            return False

                    elif 'ORIGIN' in hdulist[0].header:
                        if hdulist[0].header['ORIGIN'] == 'ESO-MIDAS':
                            prihdr = hdulist[1].data
                            s.set_data([prihdr['LAMBDA']*10, prihdr['FLUX'], prihdr['ERR']])
                    elif 'DLA_PASQ' in hdulist[0].header:
                        prihdr = hdulist[0].data
                        x = np.logspace(hdulist[0].header['CRVAL1'], hdulist[0].header['CRVAL1']+0.0001*hdulist[0].header['NAXIS1'], hdulist[0].header['NAXIS1'])
                        s.set_data([x, prihdr[0], prihdr[1]])
                    elif 'HIERARCH ESO PRO CATG' in hdulist[0].header:
                        #print(hdulist[0].header['HIERARCH ESO PRO CATG'])
                        if hdulist[0].header['HIERARCH ESO PRO CATG'] == 'MOS_SCIENCE_REDUCED':
                            x = np.linspace(hdulist[0].header['CRVAL1'], hdulist[0].header['CRVAL1']+hdulist[0].header['CDELT1']*(hdulist[0].header['NAXIS1']-1), hdulist[0].header['NAXIS1'])
                            s.set_data([x, hdulist[0].data[0]*1e20, np.ones_like(x)])
                    elif 'UVES_popler' in str(hdulist[0].header['HISTORY']):
                        header = hdulist[0].header
                        if 'LOGLIN' in header['CTYPE1']:
                            x = 10 ** (header['CRVAL1'] + np.arange(header['NAXIS1'] + 1 - header['CRPIX1']) * header['CD1_1'])

                        elif 'LINEAR' in header['CTYPE1']:
                            pass
                        err = hdulist[0].data[1, :]
                        err[err < 0] = 0
                        s.set_data([x, hdulist[0].data[0, :], err])
                    else:
                        prihdr = hdulist[1].data
                        if 1:
                            #print(prihdr.dtype)
                            s.set_data([prihdr['lam'] * 10000, prihdr['trans']])
                        else:
                            print(type(prihdr), prihdr.field('LAMBDA'))
                            s.set_data([prihdr['LAMBDA'] * 10000, prihdr['FLUX']])
                        try:
                            if 'BINTABLE' in hdulist[2].header['XTENSION']:
                                prihdr = hdulist[2].data
                                s.set_data([prihdr[0][0][:], prihdr[0][1][:], prihdr[0][2][:]])
                        except:
                            print('aborted Hadi fits')
                            return False
                else:
                    try:
                        args = line.split()
                        f, header = open(args[0], 'r'), 0
                        while f.readline().startswith('#'):
                            header += 1
                        data = np.genfromtxt(args[0], skip_header=header, unpack=True)
                        #data[1] *= scale_factor
                        #if len(data) > 2:
                        #    data[2] *= scale_factor
                        s.set_data(data)

                        if len(args) == 2:
                            s.resolution = int(args[1])
                            print('resolution: ', args[1])

                    except Exception as inst:
                        #print(type(inst))    # the exception instance
                        #print(inst.args)     # arguments stored in .args
                        #print(inst)
                        #print('aborted dat')
                        #raise Exception
                        return False

            else:
                s.set_data(spec)

            s.wavelmin = np.min(s.spec.raw.x)
            s.wavelmax = np.max(s.spec.raw.x)
            self.s.append(s)
        if append:
            self.plot.vb.disableAutoRange()
            self.s.redraw()
        else:
            self.s.draw()
            
        if self.SDSS_filters_status:
            m = max([max(s.spec.raw.y) for s in self.s])
            for f in self.sdss_filters:
                f.update(m)

    def import2dSpectrum(self, filelist, spec=None, header=0, dir_path='', ind=None, append=False):

        if isinstance(filelist, str):
            filelist = [filelist]

        for line in filelist:
            filename = line.split()[0]
            print(filename)
            if ind is not None:
                self.s.ind = ind
            else:
                self.s.append(Spectrum(self, name=filename))
                self.s.ind = len(self.s) - 1

            s = self.s[self.s.ind]

            if spec is None:
                if ':' not in filename:
                    filename = dir_path + filename

                if filename.endswith('.fits'):
                    with fits.open(filename, memmap=False) as hdulist:
                        x = np.linspace(hdulist[0].header['CRVAL1'],
                                        hdulist[0].header['CRVAL1'] + hdulist[0].header['CDELT1'] *
                                        (hdulist[0].header['NAXIS1']-1),
                                        hdulist[0].header['NAXIS1'])
                        y = np.linspace(hdulist[0].header['CRVAL2'],
                                        hdulist[0].header['CRVAL2'] + hdulist[0].header['CDELT2'] *
                                        (hdulist[0].header['NAXIS2']-1),
                                        hdulist[0].header['NAXIS2'])
                        if 'INSTRUME' in hdulist[0].header and 'XSHOOTER' in hdulist[0].header['INSTRUME']:
                            err, mask = None, None
                            for h in hdulist[1:]:
                                if h.header['EXTNAME'].strip() == 'ERRS':
                                    err = h.data * 1e17
                                if h.header['EXTNAME'].strip() == 'QUAL':
                                    mask = h.data.astype(bool)
                            s.spec2d.set(x=x*10, y=y, z=hdulist[0].data*1e17, err=err, mask=mask)

                        if 'ORIGFILE' in hdulist[0].header and 'VANDELS' in hdulist[0].header['ORIGFILE']:
                            s.spec2d.set(x=x, y=y[:-1], z=hdulist[0].data[:-1,:])

                        if 'ORIGIN' in hdulist[0].header and 'sviewer' in hdulist[0].header['ORIGIN']:
                            err, mask, cr, sky, sky_mask, trace = None, None, None, None, None, None
                            for h in hdulist[1:]:
                                if h.header['EXTNAME'].strip() == 'err':
                                    err = h.data
                                if h.header['EXTNAME'].strip() == 'mask':
                                    mask = h.data.astype(bool)
                                if h.header['EXTNAME'].strip() == 'cr':
                                    cr = h.data
                                if h.header['EXTNAME'].strip() == 'sky':
                                    sky = h.data
                                if h.header['EXTNAME'].strip() == 'sky_mask':
                                    sky_mask = h.data
                                if h.header['EXTNAME'].strip() == 'trace':
                                    trace = h.data
                                    print(trace)
                            s.spec2d.set(x=x, y=y, z=hdulist[0].data, err=err, mask=mask)
                            if cr is not None:
                                s.spec2d.cr = image(x=x, y=y, mask=cr)
                            if sky is not None:
                                if sky_mask is None:
                                    if cr is not None:
                                        sky_mask = cr
                                    elif mask is not None:
                                        sky_mask = mask
                                s.spec2d.sky = image(x=x, y=y, z=sky, mask=sky_mask)
                            if trace is not None:
                                s.spec2d.trace = trace

                elif filename.endswith('.dat'):
                    s.spec2d = None

            else:
                s.spec2d.set(x=spec[0], y=spec[1], z=spec[2])

        self.s.redraw()

    def showExportDialog(self):

        fname = QFileDialog.getSaveFileName(self, 'Export spectrum', self.work_folder)

        if fname[0]:
            
            self.exportSpectrum(fname[0])
            self.statusBar.setText('Spectrum is written to ' + fname[0])

    def show2dExportDialog(self):

        self.exportData = ExportDataWidget(self, 'export2d')
        self.exportData.show()

    def showExportDataDialog(self):

        self.exportData = ExportDataWidget(self, 'export')
        self.exportData.show()
              
    def exportSpectrum(self, filename):
        if len(self.s[self.s.ind].spec.err()) > 0:
            data = np.c_[self.s[self.s.ind].spec.x(), self.s[self.s.ind].spec.y(), self.s[self.s.ind].spec.err()]
        else:
            data = np.c_[self.s[self.s.ind].spec.x(), self.s[self.s.ind].spec.y()]
        np.savetxt(filename, data, fmt='%10.5f')

    def export2dSpectrum(self, filename, opts=[]):
        s = self.s[self.s.ind].spec2d
        hdul = fits.HDUList()
        hdr = fits.Header()
        hdr['ORIGIN'] = 'sviewer'
        hdr['CRPIX1'] = 1.0
        hdr['CRVAL1'] = s.raw.x[0]
        hdr['CDELT1'] = s.raw.x[1] - s.raw.x[0]
        hdr['CTYPE1'] = 'LINEAR'
        hdr['CRPIX2'] = 1.0
        hdr['CRVAL2'] = s.raw.y[0]
        hdr['CDELT2'] = s.raw.y[1] - s.raw.y[0]
        hdr['CTYPE2'] = 'LINEAR'
        hdr_c = fits.Header()
        for opt in opts:
            hdr['EXTNAME'] = opt
            hdr_c['EXTNAME'] = opt
            if opt == 'spectrum':
                hdul.append(fits.ImageHDU(data=s.raw.z, header=hdr))
            if opt == 'err':
                if s.raw.err is not None:
                    hdul.append(fits.ImageHDU(data=s.raw.err, header=hdr))
            if opt == 'mask':
                if s.raw.mask is not None:
                    hdul.append(fits.ImageHDU(data=s.raw.mask.astype(int), header=hdr))
            if opt == 'cr':
                if s.cr is not None and s.cr.mask is not None:
                    hdul.append(fits.ImageHDU(data=s.cr.mask.astype(int), header=hdr))
            if opt == 'sky':
                if s.sky is not None:
                    hdul.append(fits.ImageHDU(data=s.sky.z, header=hdr_c))
                    hdr_c['EXTNAME'] = 'sky_mask'
                    hdul.append(fits.ImageHDU(data=s.sky.mask, header=hdr_c))
            if opt == 'trace':
                if s.trace is not None:
                    hdul.append(fits.ImageHDU(data=s.trace, header=hdr_c))
        hdul.writeto(filename, overwrite=True)

    def showImportListDialog(self):

        fname = QFileDialog.getOpenFileName(self, 'Import list of spectra', self.work_folder)

        if fname[0]:
            
            self.importListSpectra(fname[0])
            self.abs.redraw()
            self.statusBar.setText('Spectra are imported from list' + fname[0])

    def showImportFolderDialog(self):

        fname = QFileDialog.getExistingDirectory(self, "Select Directory", self.work_folder)
        print(fname)

        if fname:
            self.importFolder(fname)

    def importFolder(self, fname):
        self.work_folder = fname
        self.options('work_folder', self.work_folder)
        print([f for f in os.listdir(fname)])
        flist = os.listdir(fname)
        for fl in flist:
            if '#' in fl or '!' in fl or '%' in fl:
                flist.remove(fl)
        self.importSpectrum(flist, dir_path=fname+'/')
        self.plot.vb.enableAutoRange()
        self.abs.redraw()
        self.statusBar.setText('Spectra are imported from folder ' + fname[0])

    def importListSpectra(self, filename):
        
        self.importListFile = filename
        dir_path = os.path.dirname(filename)+'/'
        
        with open(filename) as f:
            flist = f.read().splitlines()
            for fl in flist:
                if '#' in fl or '!' in fl or '%' in fl:
                    flist.remove(fl)
            self.importSpectrum(flist, dir_path=dir_path)

        # correct error in the list given by parameters in the line
        for fl in flist:
            if len(fl.split()) > 2:
                if not any([x in fl for x in ['#', '!', '%']]):
                    for s in self.s:
                        if s.filename == fl.split()[0]:
                            s.spec.raw.err *= float(fl.split()[2])

        self.plot.vb.enableAutoRange()
        
    def showExportListDialog(self):

        fname = QFileDialog.getOpenFileName(self, 'Export list of spectra', self.work_folder)

        if fname[0]:
            self.statusBar.setText('Spectrum list are written to ' + fname[0])

    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    # >>>
    # >>>   View routines
    # >>>
    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>

    def showExpList(self):
        if self.exp is None:
            self.exp = expTableWidget(self)
            self.exp.show()
        else:
            self.exp.close()

    def showResidualsPanel(self, show=None):
        if show is None:
            self.show_residuals = not self.show_residuals
        else:
            self.show_residuals = show
        self.options('show_residuals', bool(self.show_residuals))
        if self.show_residuals:
            self.residualsPanel = residualsWidget(self)
            self.splitter_plot.insertWidget(0, self.residualsPanel)
            if self.show_2d:
                self.splitter_plot.setSizes([450, 1000, 1000])
            else:
                self.splitter_plot.setSizes([450, 1900])
            if len(self.s) > 0:
                self.s.redraw()
        else:
            if hasattr(self, 'residualsPanel'):
                self.residualsPanel.hide()
                self.residualsPanel.deleteLater()
                del self.residualsPanel

    def show2dPanel(self, show=None):
        print(show)
        if show is None:
            self.show_2d = not self.show_2d
        else:
            self.show_2d = show
        self.options('show_2d', bool(self.show_2d))
        if self.show_2d:
            self.spec2dPanel = spec2dWidget(self)
            if self.show_residuals:
                self.splitter_plot.insertWidget(1, self.spec2dPanel)
                self.splitter_plot.setSizes([450, 1000, 1000])
            else:
                self.splitter_plot.insertWidget(0, self.spec2dPanel)
                self.splitter_plot.setSizes([1000, 1000])
            if len(self.s) > 0:
                self.s.redraw()
        else:
            if hasattr(self, 'spec2dPanel'):
                self.spec2dPanel.hide()
                self.spec2dPanel.deleteLater()
                del self.spec2dPanel

    def showPreferences(self):
        if self.preferences is None:
            self.preferences = preferencesWidget(self)
        else:
            self.preferences.close()

    def showLines(self, show=True):
        self.showlines = showLinesWidget(self)
        print(show)
        if show:
            self.showlines.show()

    def takeSnapShot(self):
        self.snap = snapShotWidget(self)
        #self.snap.show()

    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    # >>>
    # >>>   Observational routines
    # >>>
    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>


    def chooseUVESSetup(self):
        if not self.UVESSetup.isChecked():
            self.UVESSetup_status = -1
        else:
            try:
                self.vb.removeItem(self.UVES_setup.gobject)
                self.vb.removeItem(self.UVES_setup.label)
            except:
                pass

            self.UVESSetups = UVESSetups()
            if (self.UVESSetup_status == -1):
                self.UVESSetup_status = 0
            self.UVES_setup = UVESSet(self, name=list(self.UVESSetups.items())[self.UVESSetup_status][0])

            m = max([max(s.spec.y()) for s in self.s])
            self.UVES_setup.set_gobject(m)
            self.vb.addItem(self.UVES_setup.gobject)
            self.vb.addItem(self.UVES_setup.label)

    def addUVESetc(self):
        fname = QFileDialog.getOpenFileName(self, 'Import ETC data', self.work_folder)
        self.work_folder = os.path.dirname(fname[0])
        self.options('work_folder', self.work_folder)
        data = np.genfromtxt(fname[0], skip_header=2, unpack=True)
        s = Spectrum(self, name=fname[0])
        s.set_data([data[6]*10, data[12], np.ones_like(data[6])])
        s.wavelmin = np.min(s.spec.x())
        s.wavelmax = np.max(s.spec.x())
        self.s.append(s)
        self.s.redraw()

    def observability(self):
        cand = []
        for s in self.SDSSdata:
            cand.append(obsobject(s['name'], s['ra'], s['dec']))
        observability(cand)

    #>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    #>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    #>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    # >>>
    # >>>   Fit routines
    # >>>
    #>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    #>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    #>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>

    def normalize(self, state=None):
        if self.normview != state:
            if state == None:
                self.normview = not self.normview
            else:
                self.normview = state
            self.panel.normalize.setChecked(self.normview)
            self.s.normalize()
            # self.parent.abs.redraw()
            x = self.plot.vb.getState()['viewRange'][0]
            self.plot.vb.enableAutoRange()
            try:
                self.plot.set_range(x[0], x[-1])
                self.abs.redraw()
            except:
                pass

    def setFitModel(self):
        if self.fitModel is None:
            self.fitModel = fitModelWidget(self)
            self.fitModel.show()
        else:
            self.fitModel.close()

    def chooseFitPars(self):

        if self.chooseFit is None:
            self.chooseFit = chooseFitParsWidget(self)
            self.splitter_fit.insertWidget(1, self.chooseFit)
            self.splitter_fit.setSizes([2500, 170])
            self.chooseFit.show()
        else:
            self.chooseFit.close()
            self.chooseFit = None

    def showFit(self, ind=-1, all=True):
        if 1:
            f = not self.normview
            if f:
                self.normalize()
            self.s.prepareFit(ind, all=all)
            self.s.calcFit(ind, redraw=True)
            self.s.calcFitComps()
            self.s.chi2()
            if f:
                self.normalize()
        else:
            self.s.calcFitfast(ind, redraw=True)
        try:
            self.fitModel.refresh()
        except:
            pass
        self.s.redraw()

    def setFit(self, comp=-1):
        for par in self.fit.list():
            if comp == -1 or (par.sys is not None and par.sys.ind == comp):
                par.fit = par.vary
            else:
                par.fit = False
        print(self.fit.list_fit())

    def fitLM(self, comp=-1):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.panel.fitbutton.setChecked(True)
        if self.chiSquare.text().strip() == '':
            print('showFit')
            self.showFit()

        if self.animateFit:
            if 1:
                self.thread = threading.Thread(target=self.LM, args=(), kwargs={'comp': comp}, daemon=True)
                self.thread.start()
            else:
                self.fitprocess = Process(target=self.LM) #s, args=(comp,))
                self.fitprocess.daemon = True
                self.fitprocess.start()
        else:
            self.LM(comp=comp)
        self.panel.fitbutton.setChecked(False)
        QApplication.restoreOverrideCursor()

    def fitGrid(self, num=None):
        if not self.normview:
            self.normalize()
        self.s.prepareFit(all=all)

        if len(self.fit.list_fit()) == 1:
            p = str(self.fit.list_fit()[0])
            print(p)
            if num is not None:
                pg = np.linspace(self.fit.getValue(p, 'min'), self.fit.getValue(p, 'max'), num)
            else:
                pg = np.linspace(self.fit.getValue(p, 'min'), self.fit.getValue(p, 'max'), int((self.fit.getValue(p, 'max') - self.fit.getValue(p, 'min')) / self.fit.getValue(p, 'step'))+1)
            lnL = np.zeros(pg.size)
            for i, v in enumerate(pg):
                print(i, v)
                self.fit.setValue(p, v)
                self.s.prepareFit(all=False)
                self.s.calcFit(recalc=True)
                lnL[i] = self.s.chi2()

            d = distr1d(pg, np.exp(np.min(lnL.flatten())-lnL))
            d.dopoint()
            d.plot(conf=0.683)

            self.fit.setValue(p, d.point)

        if len(self.fit.list_fit()) == 2:
            p1, p2 = str(self.fit.list_fit()[0]), str(self.fit.list_fit()[1])
            psv1, psv2 = self.fit.getValue(p1), self.fit.getValue(p2)

            if num is not None:
                pg1 = np.linspace(self.fit.getValue(p1, 'min'), self.fit.getValue(p1, 'max'), num)
                pg2 = np.linspace(self.fit.getValue(p2, 'min'), self.fit.getValue(p2, 'max'), num)
            else:
                pg1 = np.linspace(self.fit.getValue(p1, 'min'), self.fit.getValue(p1, 'max'), int((self.fit.getValue(p1, 'max') - self.fit.getValue(p1, 'min')) / self.fit.getValue(p1, 'step'))+1)
                pg2 = np.linspace(self.fit.getValue(p2, 'min'), self.fit.getValue(p2, 'max'), int((self.fit.getValue(p2, 'max') - self.fit.getValue(p2, 'min')) / self.fit.getValue(p2, 'step'))+1)
            print(pg1, pg2)
            lnL = np.zeros((pg2.size, pg1.size))
            for i1, v1 in enumerate(pg1):
                print(i1)
                self.fit.setValue(p1, v1)
                for i2, v2 in enumerate(pg2):
                    self.fit.setValue(p2, v2)
                    self.s.prepareFit(all=False)
                    self.s.calcFit(recalc=True)
                    lnL[i2, i1] = self.s.chi2()


            d = distr2d(pg1, pg2, np.exp(np.min(lnL.flatten())-lnL))
            #d = distr2d(pg1, pg2, np.exp(- lnL / np.min(lnL.flatten())))
            d.plot_contour(conf_levels=[0.683, 0.954], xlabel=p1, ylabel=p2)

            self.fit.setValue(p1, d.point[0])
            self.fit.setValue(p2, d.point[1])

        self.s.calcFit(recalc=True, redraw=True)
        self.s.chi2()

        plt.show()


    def LM(self, comp=-1, timer=True, redraw=True):
        t = Timer(verbose=True) if 1 else False

        def fcn2min(params):
            for p in params:
                name = params[p].name.replace('l2', '**').replace('l1', '*') #this line is added since lmfit doesn't recognize '*' mark\
                self.fit.setValue(name, self.fit.pars()[name].ref(params[p].value))
            self.fit.update(redraw=False)
            if timer:
                t.time('in')

            self.s.prepareFit(ind=comp, all=False)
            self.s.calcFit(recalc=True, redraw=self.animateFit)

            if timer:
                tim = t.time('out')
                if self.animateFit:
                    t.sleep(max(0, 0.02-tim))

            return self.s.chi()

        # create a set of Parameters
        params = Parameters()
        for par in self.fit.list():
            if not par.fit or not par.vary:
                par.unc = None
        for par in self.fit.list_fit():
            p = str(par).replace('**', 'l2').replace('*', 'l1')  #this line is added since lmfit doesn't recognize '*' mark
            print(p)
            value, pmin, pmax = par.ref()  #par.val, par.min, par.max
            print(par.ref())
            if 'cf' in p:
                pmin, pmax = 0, 1
            params.add(p, value=value, min=pmin, max=pmax)

        # do fit, here with leastsq model
        minner = Minimizer(fcn2min, params)
        kws = {'options': {'maxiter': 10}}
        result = minner.minimize(maxfev=200)

        # calculate final result
        print(result.success, result.var_names, result.params, result.covar, result.errorbars, result.message)
        #final = data + result.residual

        # write error report
        report_fit(result)
        #ci = conf_interval(minner, result)
        #printfuncs.report_ci(ci)

        self.showFit(all=False)

        self.fit.fromLMfit(result)

        self.console.set(fit_report(result))
        return fit_report(result)

    def fitMCMC(self):
        if self.MCMC is None:
            self.MCMC = fitMCMCWidget(self)
            self.MCMC.show()
        else:
            self.MCMC.raise_()

    def stopFit(self):
        """
        stop executing fit process
        """
        if self.fitprocess is not None:
            self.fitprocess.terminate()
            self.fitprocess.join()
            self.fitprocess = None
        if self.thread.is_alive():
            self.thread.join()

    def showFitResults(self):

        if self.fitResults is None:
            self.fitResults = fitResultsWidget(self)
            self.fitResults.show()
        else:
            self.fitResults.refresh()

    def calc_cont(self):
        x = self.plot.vb.getState()['viewRange'][0]
        self.s[self.s.ind].calc_cont(x[0], x[-1])

    def fitCheb(self, typ='cheb'):
        """
        fit Continuum using specified model.
            - kind        : can be 'cheb', 'GP',
        """
        s = self.s[0]
        mask = (s.spec.x() > self.fit.cont_left) * (s.spec.x() < self.fit.cont_right)
        fit = s.fit.f(s.spec.x())
        mask = np.logical_and(fit > 0.05, s.fit_mask.x)
        x = s.norm.x[mask]
        y = s.norm.y[mask] / fit[mask]
        w = s.norm.err[mask] / fit[mask]
        fig, ax = plt.subplots()
        ax.errorbar(x, y, yerr=w, fmt='o')

        if typ == 'cheb':
            cheb = np.polynomial.chebyshev.Chebyshev.fit(x, y, self.fit.cont_num - 1, w=1.0/w)
            poly = np.polynomial.chebyshev.cheb2poly([c for c in cheb])
            for i, c in enumerate(cheb):
                self.fit.setValue('cont_' + str(i), c)
            ax.plot(x, self.s[0].correctContinuum(x), '-r')

        elif typ == 'GP':
            import pyGPs
            model = pyGPs.GPR()
            model.getPosterior(x, y)
            model.optimize(x, y)
            z = np.linspace(x[0], x[-1], len(x) * 2)
            model.predict(z)
            ym = np.reshape(model.ym, (model.ym.shape[0],))
            ys2 = np.reshape(model.ys2, (model.ys2.shape[0],))
            ax.plot(z, ym, color='g', ls='-', lw=3.)
            # print(z, ym, ym - 2. * np.sqrt(ys2), ym + 2. * np.sqrt(ys2))
            ax.fill_between(z, ym - 2. * np.sqrt(ys2), ym + 2. * np.sqrt(ys2),
                            facecolor='g', alpha=0.4, linewidths=0.0)
            # model.plot()

        plt.show()

    def fitExt(self):
        self.fitExtWindow = fitExtWidget(self)
        self.fitExtWindow.show()

    def fitGauss(self):
        """
        fit spectrum with simple gaussian line (emission)
        """
        for s in self.s:
            n = np.sum(s.mask)
            if  n > 0:
                x, y = s.spec.x[s.mask], s.spec.y[s.mask]
                mean = self.line_reper.l*(1+self.z_abs)
                sigma = 10
                print(mean, sigma)
                def gaus(x,a,x0,sigma):
                    return a*np.exp(-(x-x0)**2/(2*sigma**2))
                popt, pcov = curve_fit(gaus, x, y, p0=[1, mean, sigma])
                print(gaus(x, *popt))
                self.plot.add_line(x, gaus(x, *popt))
                print(quad(gaus, x[0], x[-1], args=tuple(popt)))

    def fitPowerLaw(self):
        if not self.normview:
            s = self.s[self.s.ind]
            x = np.log10(s.spline.x)
            y = np.log10(s.spline.y)

            p = np.polyfit(x, y, 1)
            print(p)

            x = np.logspace(np.log10(s.spec.x()[0]), np.log10(s.spec.x()[-1]), 100)
            y = np.power(10, p[1] + np.log10(x)*p[0])
            s.cont.set_data(x=x, y=y)
            s.redraw()

    def fitPoly(self, deg=None, typ='cheb'):
        """
        Fitting the selected points region with Polynomial function
        :param deg:  degree of polynmial function
        :param typ:  type of polynomial function, can be 'cheb' for Chebyshev, 'x' for simple polynomial
        :return: None
        """

        s = self.s[self.s.ind]
        x = s.spec.x()[s.fit_mask.x()]
        y = s.spec.y()[s.fit_mask.x()]
        w = s.spec.err()[s.fit_mask.x()]

        #self.fit.cont_fit = True
        #s.redraw()

        if deg is not None:
            self.options('polyDeg', deg)

        if typ == 'x':
            p = np.polyfit(x, y, self.polyDeg, w=1.0/w)
        elif typ == 'cheb':
            cheb = np.polynomial.chebyshev.Chebyshev.fit(x, y, self.polyDeg, w=1.0/w)

        x = np.linspace(x[0], x[-1], 100)

        if typ == 'x':
            y = np.polyval(p, x)
        elif typ == 'cheb':
            base = (x - x[0]) * 2 / (x[-1] - x[0]) - 1
            y = np.polynomial.chebyshev.chebval(base, [c for c in cheb])

        if self.normview:
            s.set_cheb(x=x, y=y)
        else:
            s.cont_mask = (s.spec.raw.x > x[0]) & (s.spec.raw.x < x[-1])
            s.cont.set_data(x=x, y=y)
            s.cont.interpolate()
            s.cont.set_data(x=s.spec.raw.x[s.cont_mask], y=s.cont.inter(s.spec.raw.x[s.cont_mask]))
            s.g_cont.setData(x=s.cont.x, y=s.cont.y)

    def fitMinEnvelope(self, res=200):

        s = self.s[self.s.ind]
        x, y = s.spec.x(), s.spec.y()
        if 1:
            mask = np.ones_like(x, dtype=bool)
            for r in self.regions:
                mask *= 1 - (x > r[0]) * (x < r[1])
            x, y = x[mask], y[mask]
        #w = s.spec.err()[s.fit_mask.x()]

        fig, ax = plt.subplots()
        ax.plot(x, y, '-b')

        # >>> convolve flux
        y = convolveflux(x, y, res=res, kind='direct')
        ax.plot(x, y, '--g')

        # >>> find local minima
        inds = np.where(np.r_[True, y[1:] < y[:-1]] & np.r_[y[:-1] < y[1:], True])[0]
        for i, c in zip(range(3), ['gold', 'magenta', 'red']):
            ax.plot(x[inds], y[inds], 'o', c=c)

            ys = sg.savitzky_golay(y[inds], window_size=5, order=3)
            inter = interp1d(x[inds], ys, bounds_error=False, fill_value=(ys[0], ys[-1]))
            ax.plot(x, inter(x), '-', c=c)

            inds = np.delete(inds, np.where((ys - y[inds]) / np.std(ys - y[inds]) < -1)[0])

        plt.show()

    def H2ExcDiag(self):
        """
        Show H2 excitation diagram for the selected component 
        """
        data = np.genfromtxt('data/H2/energy_X.dat', comments='#', unpack=True)
        fig, ax = plt.subplots(figsize=(6,7))
        num_sys = 0
        text = []
        for sys in self.fit.sys:
            label = 'sys_'+str(self.fit.sys.index(sys)+1)
            label = 'z = '+str(sys.z.str(attr='val')[:8])
            if any(['H2' in name for name in sys.sp.keys()]):
                num_sys += 1
                x, y = [], []
                for sp in sys.sp:
                    if 'H2' in sp:
                        m = np.logical_and(data[0] == 0, data[1] == int(sp[3:]))
                        x.append(float(data[2][m]))
                        #x.append(self.atomic[sp].energy)
                        y.append(copy(sys.sp[sp].N.unc).log() - np.log10(self.atomic[sp].statw()))
                        y[-1].log()
                        y[-1].val = sys.sp[sp].N.val - np.log10(self.atomic[sp].statw())
                arg = np.argsort(x)
                x = np.array(x)[arg]
                y = np.array(y)[arg]

                p = ax.plot(x, [v.val for v in y], 'o', markersize=1) #, label='sys_' + str(self.fit.sys.index(sys)))
                ax.errorbar(x, [v.val for v in y], yerr=[[v.plus for v in y], [v.minus for v in y]],  fmt='o', color = p[0].get_color(), label=label)
                #temp = self.H2ExcitationTemp(levels=[0, 1], ind=self.fit.sys.index(sys), plot=False, ax=ax)
                text.append(self.H2ExcitationTemp(levels=[0, 1], E=500, ind=self.fit.sys.index(sys), plot=False, ax=ax))

        adjust_text([t[2] for t in text], [t[0] for t in text], [t[1] for t in text], ax=ax)
        ax.set_xlabel(r'Energy, cm$^{-1}$')
        ax.set_ylabel(r'$\log\, N$ / g')
        ax.xaxis.set_minor_locator(AutoMinorLocator(5))
        #ax.xaxis.set_major_locator(self.x_locator)
        ax.yaxis.set_minor_locator(AutoMinorLocator(5))
        #ax.yaxis.set_major_locator(self.y_locator)

        print(num_sys)
        if num_sys > 1:
            ax.legend(loc='best')
        fig.tight_layout()
        plt.savefig(os.path.dirname(os.path.realpath(__file__)) + '/output/H2_exc.pdf', bbox_inches='tight')
        plt.show()
        self.statusBar.setText('Excitation diagram for H2 rotational level for {:d} component is shown'.format(self.comp))

    def H2ExcitationTemp(self, levels=[0, 1, 2], E=None, ind=None, plot=True, ax=None):
        from ..excitation_temp import ExcitationTemp

        for i, sys in enumerate(self.fit.sys):
            if ind is None or ind == i:
                print(levels, ['H2j'+str(x) in sys.sp.keys() for x in levels])
                if all(['H2j'+str(x) in sys.sp.keys() for x in levels]):
                    temp = ExcitationTemp('H2')
                    # print(Temp.col_dens(num=4, Temp=92, Ntot=21.3))
                    n = [sys.sp['H2j'+str(x)].N.unc for x in levels]
                    if any([ni.val == 0 for ni in n]):
                        n = [a(sys.sp['H2j'+str(x)].N.val, 0, 0) for x in levels]
                    temp.calcTemp(n, calc='', plot=plot, verbose=1)
                    if E == None:
                        E = temp.E
                    elif isinstance(E, (float, int)):
                        E = np.asarray([0, E])
                    elif isinstance(E, list):
                        E = np.asarray(E)
                    if ax is not None:
                        if temp.slope.type == 'm':
                            ax.plot(E / 1.4388 * 1.5, temp.slope.val * E * 1.5 + temp.zero.val, '--k', lw=1.5)
                            text = [E[-1] / 1.4388 * 1.5, temp.slope.val * E[-1] * 1.5 + temp.zero.val,
                                    'T$_{' + ''.join([str(l) for l in levels]) + '}$=' + temp.latex(f=0, base=0)+'K']
                        elif temp.slope.type == 'u':
                            E = np.linspace(E[0], E[1], 5)
                            ax.errorbar(E / 1.4388 * 1.5, (temp.slope.val - temp.slope.minus) * E * 1.5 + temp.zero.val, fmt='--k', yerr=0.1, lolims=E>0, lw=1.5, capsize=0, zorder=0 )
                            text = [E[-1] / 1.4388 * 1.5, temp.slope.val * E[-1] * 1.5 + temp.zero.val,
                                    'T$_{' + ''.join([str(l) for l in levels]) + '}$>' + '{:.0f}'.format(temp.temp.dec().val) + 'K']
                        text[2] = ax.text(text[0], text[1], text[2], va='top', ha='right', fontsize=16)
        if plot:
            plt.show()

        return text
        #if ind is not None:
        #    return temp.temp

    def showMetalAbundance(self, component=1, dep_ref='ZnII', HI=a(21,0,0)):
        """
        Show metal abundances, metallicity and depletions based on the fit
        """
        colors = ['royalblue', 'orangered', 'seagreen', 'darkmagenta', 'skyblue', 'paleviotelred', 'chocolate']

        names = set()
        for sys in self.fit.sys:
            for sp in sys.sp.keys():
                names.add(sp)
        refs = set(names)
        for sys in self.fit.sys:
            refs = refs & sys.sp.keys()
        names = list(names)

        if 0:
            inds = np.argsort([condens_temperature(name) for name in names])
            names = [names[i] for i in inds]

        ref = list(refs)[0]

        print(names, refs, ref)

        for sys in self.fit.sys:
            for sp in sys.sp.keys():
                if sys.sp[sp].N.unc is None or sys.sp[sp].N.unc.val == 0:
                    sys.sp[sp].N.unc = a(sys.sp[sp].N.val, 0, 0)

        if component:
            fig, ax = plt.subplots()

            for sys in self.fit.sys:
                color = colors[self.fit.sys.index(sys)]
                m = metallicity(ref, sys.sp[ref].N.unc, 22.0)
                for i, sp in enumerate(names):
                    if sp in sys.sp.keys():
                        y = metallicity(sp, sys.sp[ref].N.unc, 22.0) / m
                        ax.scatter(i, y.val, c=color)
                        ax.errorbar([i], [y.val], yerr=[[y.minus], [y.plus]], c=color)
            ax.set_xticks(np.arange(len(names)))
            ax.set_xticklabels(names)
            plt.draw()

            fig, ax = plt.subplots()

            for sys in self.fit.sys:
                color = colors[self.fit.sys.index(sys)]
                if dep_ref in sys.sp.keys():
                    for k, v in sys.sp.items():
                        y = depletion(k, v.N.unc, sys.sp[dep_ref].N.unc, ref=dep_ref)
                        ax.scatter(names.index(k), y.val, c=color)
                        ax.errorbar([names.index(k)], [y.val], yerr=[[y.minus], [y.plus]], c=color)

            ax.set_xticks(np.arange(len(names)))
            ax.set_xticklabels(names)
            plt.show()

        sp = {}
        for name in names:
            if name not in self.fit.total.sp.keys():
                sp[name] = a(0, 0, 'd')
                for sys in self.fit.sys:
                    if name in sys.sp.keys():
                        print(name, sys.sp[name].N.unc)
                        sp[name] += sys.sp[name].N.unc
                sp[name].log()
                self.fit.total.addSpecies(name)
                self.fit.total.sp[name].N.unc = sp[name]
            else:
                sp[name] = self.fit.total.sp[name].N.unc

        res = {}
        for k, v in sp.items():
            if dep_ref is '':
                res[k] = [v]
            else:
                res[k] = [v, metallicity(k, v, HI), depletion(k, v, sp[dep_ref], ref=dep_ref)]
            print('SMA', k, res[k])

        return res

    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    # >>>
    # >>>   1d spec routines
    # >>>
    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>

    def fitCont(self):
        if self.fitContWindow is None:
            self.fitContWindow = fitContWidget(self)
            self.fitContWindow.show()
        else:
            self.fitContWindow.close()

    def rescale(self):

        if self.rescale_ind == 0:

            s = self.s[self.s.ind]

            #x = s.spec.raw.x[s.cont_mask]
            y = s.spec.raw.y[s.cont_mask] / s.cont.y
            #err = s.spec.raw.err[s.cont_mask] / s.cont.y

            window = 20
            mean = smooth(y, window_len=window, window='flat', mode='same')
            square = smooth(y**2, window_len=window, window='flat', mode='same')
            std = np.sqrt(square - mean**2)

            mask_0 = (y < 1.5 * std)
            mask_1 = (np.abs(y - 1) < 1.5 * std)

            self.s.append(Spectrum(self, 'error_0', data=[s.cont.x[mask_0], std[mask_0], std[mask_0]/np.sqrt(window)]))
            self.s.append(Spectrum(self, 'error_1', data=[s.cont.x[mask_1], std[mask_1], std[mask_1]/np.sqrt(window)]))
            self.s.redraw(len(self.s) - 1)

        if self.rescale_ind == 1:

            s0 = self.s[self.s.find('error_0')]
            s1 = self.s[self.s.find('error_1')]

            inter0 = interp1d(s0.cont.x, s0.cont.y, fill_value='extrapolate')
            inter1 = interp1d(s1.cont.x, s1.cont.y, fill_value='extrapolate')
            s = self.s[self.s.ind]
            y = s.spec.raw.y / s.cont.y
            s.spec.raw.err = s.cont.y * (inter0(s.spec.raw.x) * (1 - np.abs(y)) + inter1(s.spec.raw.x) * np.abs(y))

            self.s.redraw()

        self.rescale_ind = 1 - self.rescale_ind

    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    # >>>
    # >>>   2d spec routines
    # >>>
    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>

    def extract2d(self):

        if self.extract2dwindow is None:
            self.extract2dwindow = extract2dWidget(self)
            self.extract2dwindow.show()
        else:
            self.extract2dwindow.close()

    #>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    #>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    #>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    # >>>
    # >>>   Combine routines
    # >>>
    #>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    #>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    #>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>

    def showExpListCombine(self):
        
        if hasattr(self, 'importListFile'):
            dtype = [('filename', np.str_, 100), ('DATE-OBS', np.str_, 20), 
                     ('WAVELMIN', np.float_), ('WAVELMAX', np.float_),
                     ('EXPTIME', np.float_), ('SPEC_RES', np.int_)]
            zero = ('', '', np.nan, np.nan, np.nan, 0)
            x = np.array([zero], dtype=dtype)
            i = 0
            with open(self.importListFile) as f:
                flist = f.read().splitlines() 
                dir_path = os.path.dirname(self.importListFile)+'/'
                for filename in flist:
                    if ':' not in filename:
                        filename = dir_path+filename
                    if '.fits' in filename:
                        if i:
                            x = np.insert(x, len(x), zero, axis=0)
                        i = 1
                        x[-1]['filename'] = os.path.basename(filename)
                        hdulist = fits.open(filename)
                        header = hdulist[0].header
                        for d in dtype[1:]:
                            try:
                                x[-1][d[0]] = header[d[0]]
                            except:
                                pass
            self.statusBar.setText('List of fits was loaded')
        
            if len(x) > 0:
                self.expListView = ShowListImport(self, 'fits')
                self.expListView.setdata(x)
                self.expListView.show()
            
    def selectCosmics(self):
        self.s.selectCosmics()
        
    def calcSmooth(self):
        self.s.calcSmooth()
        
    def coscaleExposures(self):
        self.s.coscaleExposures()

    def shiftExposure(self):
        pass

    def rescaleExposure(self):
        pass

    def rescaleErrs(self):
        print('rescale err', self.s.ind)
        fig, ax = plt.subplots()
        s = self.s[self.s.ind]
        x = s.spec.raw.x[s.cont_mask]
        print(s.cont_mask)
        f = (s.spec.raw.y[s.cont_mask] - s.cont.y) / s.spec.raw.err[s.cont_mask]
        ax.hist(f, bins=np.linspace(np.min(f), np.max(f), int((np.max(f) - np.min(f))/0.3)+1))
        m = np.abs(f) < 5
        mean, std = np.mean(f[m]), np.std(f[m])
        print(mean, std)
        xmin, xmax = mean - 1 * std, mean + 3 * std
        m = (xmin < f) * (f < xmax)
        kde = gaussian_kde(f[m])
        x = np.linspace(xmin, xmax, np.sqrt(len(f[m])))
        fig, ax = plt.subplots()
        ax.plot(x, kde(x), '-r')

        if 1:
            n = len(x)

            def gauss(x, a, x0, sigma):
                return a * np.exp(-(x - x0) ** 2 / (2 * sigma ** 2))
            popt, pcov = curve_fit(gauss, x, kde(x), p0=[2 * std**2, mean, std])

            y = gauss(x, popt[0], popt[1], popt[2])
            ax.plot(x, y, '-k')
            print(popt)

        self.s[self.s.ind].spec.raw.err *= popt[2]
        plt.show()

    def crosscorrExposures(self, i1, i2, dv=50):
        self.s[i1].crosscorrExposures(i2, dv=dv)

    def combine(self, typ='mean'):
        """
        combine exposures
        parameters:
            - typ        :  type of combine, can be either 'mean', 'weighted mean' or 'median' 
        """

        self.combineWidget = combineWidget(self)
        self.combineWidget.show()

    def rebin(self):
        
        self.rebinWidget = rebinWidget(self)
        self.rebinWidget.show()

    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    # >>>
    # >>>   SDSS routines
    # >>>
    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>

    def loadSDSS(self, plate=None, MJD=None, fiber=None, name=None, z_abs=0):
        out = True
        print(self.SDSScat)
        if self.SDSScat == 'DR12':
            try:
                sdss = self.IGMspec['BOSS_DR12']

                if name is None or name is '':
                    ind = np.where((sdss['meta']['PLATE'] == int(plate)) & (sdss['meta']['FIBERID'] == int(fiber)))[0][0]
                else:
                    name = name.replace('J', '').replace('SDSS', '').strip()
                    ra, dec = (name[:name.index('+')], name[name.index('+'):]) if '+' in name else (name[:name.index('-')], name[name.index('-'):])
                    ra, dec = hms_to_deg(ra), dms_to_deg(dec)
                    print(ra, dec)
                    ind = np.argmin((sdss['meta']['RA_GROUP'] - ra) ** 2 + (sdss['meta']['DEC_GROUP'] - dec) ** 2)
                print(sdss['meta'][ind]['SPEC_FILE'].decode('UTF-8'))
                self.importSpectrum(sdss['meta'][ind]['SPEC_FILE'].decode('UTF-8'), spec=[sdss['spec'][ind]['wave'], sdss['spec'][ind]['flux'],
                                                 sdss['spec'][ind]['sig']])
                resolution = int(sdss['meta'][ind]['R'])
            except:
                out = False
        elif self.SDSScat == 'DR14':
            try:
                sdss = self.SDSSDR14['meta']

                if name is None or name.strip() == '':
                    ind = np.where((sdss['meta']['PLATE'] == int(plate)) & (sdss['meta']['FIBERID'] == int(fiber)))[0][0]
                else:
                    name = name.replace('J', '').replace('SDSS', '').strip()
                    ra, dec = (name[:name.index('+')], name[name.index('+'):]) if '+' in name else (name[:name.index('-')], name[name.index('-'):])
                    ra, dec = hms_to_deg(ra), dms_to_deg(dec)
                    ind = np.argmin((sdss['meta']['RA'] - ra) ** 2 + (sdss['meta']['DEC'] - dec) ** 2)
                plate, fiber = sdss['meta']['PLATE'][ind], sdss['meta']['FIBERID'][ind]
                spec = self.SDSSDR14['data/{0:04d}/{1:04d}'.format(plate, fiber)]
                mask = spec[:, 2] > 0
                self.importSpectrum('spec-{0:05d}-{1:05d}-{2:04d}'.format(plate, sdss['meta']['MJD'][ind], fiber),
                                    spec=[10**spec[:,0][mask], spec[:,1][mask], np.sqrt(1.0/spec[:,2][mask])])
                resolution = 1800
            except:
                out = False
        elif self.SDSScat == 'DR9Lee':
            pass
        else:
            out = False
        if out:
            self.s[-1].resolution = resolution
            self.vb.enableAutoRange()
            self.z_abs = z_abs
            self.abs.redraw()
            self.statusBar.setText('Spectrum is imported: ' + self.s[-1].filename)
        return out

    def loadSDSSLee(self):
        self.LeeResid = np.loadtxt('C:/Science/SDSS/DR9_Lee/residcorr_v5_4_45.dat', unpack=True)
        self.importSDSSlist('C:/science/SDSS/DR9_Lee/BOSSLyaDR9_cat.fits')
        self.SDSSlist = QSOlistTable(self, 'SDSSLee')
        self.SDSSdata = self.SDSSdata[:]
        self.SDSSlist.setdata(self.SDSSdata)
        
    def showSDSSdialog(self):
        
        self.load_SDSS = loadSDSSwidget(self)
        self.load_SDSS.show()

    def importSDSSlist(self, filename):
        if 1:
            if any([s in filename for s in ['.dat', '.txt', '.list']]):
                with open(filename) as f:
                    n = np.min([len(line.split()) for line in f])
                print(n)
                self.SDSSdata = np.genfromtxt(filename, names=True, dtype=None, unpack=True, usecols=range(n), comments='#', encoding=None)
                print(self.SDSSdata)
            elif '.fits' in filename:
                hdulist = fits.open(filename)
                data = hdulist[1].data
                self.SDSSdata = np.array(hdulist[1].data)
        else:
            self.SDSSdata = []
            data = np.genfromtxt(filename, names=True, dtype=None, unpack=True)
            for d in data:
                SDSSunit = SDSSentry(d['name'])
                for attr in data.dtype.names:
                    SDSSunit.add_attr(attr)
                    setattr(SDSSunit, attr, d[attr])
                self.SDSSdata.append(SDSSunit)
        
    def show_SDSS_list(self):
        if hasattr(self, 'SDSSdata'):
            self.SDSSlist = QSOlistTable(self, 'SDSS')
            #self.SDSSlist.show()
            self.SDSSlist.setdata(self.SDSSdata)
        else:
            self.statusBar.setText('No SDSS list is loaded')

    def search_H2(self):
        search_H2(self, z_abs=self.z_abs)

    def show_H2_cand(self):
        self.mw = MatplotlibWidget(size=(200,100), dpi=100)
        self.mw.move(QPoint(100,100))
        self.mw.show()
        figure = self.mw.getFigure()
        self.s[self.s.ind].calc_norm()
        if self.s[self.s.ind].norm.n > 0:
            self.SDSS.load_spectrum([self.s[self.s.ind].norm.x, self.s[self.s.ind].norm.y, self.s[self.s.ind].norm.err])
            self.SDSS.H2_cand.z = self.z_abs
            self.SDSS.plot_candidate(fig=figure, normalized=True)
        self.mw.draw()



    def calc_SDSS_Stack_Lee(self, typ=['cont'], ra=None, dec=None, lmin=3.5400, lmax=4.0000, snr=2.5):
        """
        Subroutine to calculate SDSS QSO stack spectrum

        parameters:
            typ        -  what type of Stack
            ra         -  Right Ascension mask (tuple of two values e.g. (20, 40) or None)
            dec        -  Declination mask (tuple of two values e.g. (20, 40) or None)
            lmin       -  loglambda minimum boundary
            lmax       -  loglambda maximum boundary
            snr        -  SNR threshold
        """

        # >>> prepare stack class to write
        delta = 0.0001
        num = int((lmax-lmin)/delta+1)
        stack = Stack(num)
        l_min = 1041
        l_max = 1185
        calc_stack = 1
        for s in self.s:
            s.remove()
        self.s = Speclist(self)
        self.specview = 'line'
        self.s.append(Spectrum(self, name='stack_cont'))
        self.s.append(Spectrum(self, name='stack_poly'))
        self.s.append(Spectrum(self, name='stack_zero'))
        self.s.append(Spectrum(self, name='cont'))
        self.s.append(Spectrum(self, name='poly'))
        self.s.append(Spectrum(self, name='mask'))

        # >>> apply mask:
        print(self.SDSSdata.dtype, self.SDSSdata['RA'], self.SDSSdata['DEC'])
        mask = np.ones(len(self.SDSSdata), dtype=bool)
        print(np.sum(mask))
        plt.hist(self.SDSSdata['RA']/180-1)
        plt.hist(self.SDSSdata['DEC'])
        plt.show()

        #ra, dec = (140, 150), (0, 60)
        if ra is not None:
            mask *= (self.SDSSdata['RA'] > ra[0]) * (self.SDSSdata['RA'] < ra[1])
        print(np.sum(mask))
        if dec is not None:
            mask *= (self.SDSSdata['DEC'] > dec[0]) * (self.SDSSdata['RA'] < dec[1])
        print(np.sum(mask))
        if snr is not None:
            mask *= self.SDSSdata['SNR_LYAF'] > snr
        print(np.sum(mask))

        if 1:
            fig, ax = plt.subplots(subplot_kw=dict(projection='aitoff'))
            ax.scatter(self.SDSSdata['RA']/180, self.SDSSdata['DEC']/180-1, s=5, marker='+')
            plt.grid(True)
            plt.show()
        else:
            for i, s in enumerate(self.SDSSdata):
                print(i, 'SNR:', s['SNR_LYAF'])
                if s['SNR_LYAF'] > snr:
                    fiber = '{:04d}'.format(int(s['FIBERID']))
                    plate = s['PLATE']
                    MJD = s['MJD']
                    filename = self.SDSSLeefolder + str(plate) + '/' + 'speclya-{0}-{1}-{2}.fits'.format(plate, MJD, fiber)
                    hdulist = fits.open(filename)

                    z = s['Z_VI']
                    hdulist[1].verify('fix')
                    if np.isnan(float(hdulist[1].header['CH_CONT'])) == False:
                        data = hdulist[1].data
                        i_min = int(max(0, (np.log10((1+z)*l_min)-data.field('LOGLAM')[0])*10000))
                        i_max = int(max(0, (np.log10((1+z)*l_max)-data.field('LOGLAM')[0])*10000))
                        if i_max > i_min:
                            res_st = int((data.field('LOGLAM')[0] - self.LeeResid[0][0])*10000)
                            #print(res_st)
                            mask = np.logical_not(data.field('MASK_COMB')[i_min:i_max])
                            #l = (10**(data.field('LOGLAM')[i_min:i_max])/lya - 1)
                            #l = 10**(data.field('LOGLAM')[i_min:i_max])
                            l = data.field('LOGLAM')[i_min:i_max]
                            corr = self.LeeResid[1][i_min+res_st:i_max+res_st] / data.field('DLA_CORR')[i_min:i_max]
                            cont = data.field('CONT')[i_min:i_max]
                            fl = data.field('FLUX')[i_min:i_max]
                            sig = (data.field('IVAR')[i_min:i_max])**(-0.5) / data.field('NOISE_CORR')[i_min:i_max]

                            p = np.polyfit(l[mask], fl[mask], 1)  # , w=np.power(sig[mask], -1))
                            p1 = np.polyfit(l[mask], fl[mask], 1, w=np.power(sig[mask], -1))
                            poly = (p[0] * l + p[1])
                            poly_sig = (p1[0] * l + p1[1])

                            imin = int(round((l[0]-lmin)/delta))
                            imax = int(round((l[-1]-lmin)/delta)+1)
                            stack.mask[imin:imax] += mask
                            stack.cont[imin:imax] += cont * mask
                            stack.poly[imin:imax] += poly * mask
                            stack.sig[imin:imax] += fl / corr / cont * mask
                            stack.sig_p[imin:imax] += fl / corr / poly * mask
                            stack.zero[imin:imax] += (fl / corr - poly) * mask / np.std((fl / corr - poly) * mask, ddof=1)

                            ston = np.mean(fl / sig)

                            stack.mask_w[imin:imax] += mask * ston
                            stack.cont_w[imin:imax] += cont * mask * ston
                            stack.poly_w[imin:imax] += poly * mask * ston
                            stack.sig_w[imin:imax] += fl / corr / cont * mask * ston
                            stack.sig_p_w[imin:imax] += fl / corr / poly * mask * ston
                            stack.zero_w[imin:imax] += (fl / corr - poly) * mask * ston / np.std((fl / corr - poly) * mask, ddof=1)
                            if 0:
                                fig, ax = plt.subplots()
                                ax.plot(l, fl, label='flux')
                                ax.plot(l, sig, label='flux/cont')
                                ax.plot(l, mask, label='mask')
                                ax.plot(l, cont, label='cont')
                                ax.plot(l, poly, label='poly')
                                ax.plot(l, corr, label='corr')
                                ax.plot(l, (fl - poly) / np.std((fl - poly) * mask, ddof=1), label='zerot')
                                ax.legend(loc='best')
                                plt.show()
        stack.masked()
        l = np.power(10, lmin+delta*np.arange(stack.n))
        for i, attr in enumerate(stack.attrs + ['mask']):
            self.s[i].set_data([l, getattr(stack, attr)])
        self.s.redraw()
        self.vb.enableAutoRange(axis=self.vb.XAxis)
        self.vb.setRange(yRange=(-2, 2))

        stack.save(l)
        if 0:
            f_Stack = open('Stack_DR9.dat', 'w')
            for i in range(len(stack)):
                f_Stack.write("%6.4f %10.4f %8.0f\n" % (lmin+delta*i, stack[i], smask[i]))

    def calc_SDSS_DLA(self):
        s_fit = SDSS_fit(self, timer=True)
        analyse = [] #['pre', 'learn']
        prefix = '_'+str(len(self.SDSSdata))

        if 'pre' in analyse:
            for i, s in enumerate(self.SDSSdata):
                SNR_Thres = 3
                print(i, 'SNR:', s['SNR_LYAF'])
                if s['SNR_LYAF'] > SNR_Thres:
                    fiber = '{:04d}'.format(int(s['FIBERID']))
                    plate = s['PLATE']
                    MJD = s['MJD']
                    s_fit.add_spec(s['SDSS_NAME'], s['Z_VI'], plate, MJD, fiber)
            print(s_fit.data)

            s_fit.preprocess()
            s_fit.SDSS_prepare()
            s_fit.SDSS_remove_outliers()
            s_fit.savetofile(['Y', 'V', 'qso'], prefix=prefix)
        else:
            s_fit.load(['Y', 'V', 'qso'], prefix=prefix)

        # plot non-NaN pixels fraction:
        if 0:
            fig, ax = plt.subplots()
            ax.plot(s_fit.l, np.sum(~np.isnan(s_fit.Y), axis=0)/s_fit.Y.shape[0])
            plt.show(block=False)

        if 'learn' in analyse:
            s_fit.calc_mean()
            s_fit.calc_covar()
            s_fit.savetofile(['m', 'M', 'w'], prefix=prefix)
        else:
            s_fit.load(['m', 'K', 'w'], prefix=prefix)

        s_fit.toGUI('mean')
        s_fit.toGUI('w')
        s_fit.plot('covar')

    def show_SDSS_filters(self):
        if self.sdss_filters is None:
            self.sdss_filters = [SpectrumFilter(self, f) for f in ['u', 'g', 'r', 'i', 'z']]
                
        self.SDSS_filters_status = not self.SDSS_filters_status
        if self.SDSS_filters_status:
            try:
                m = max([max(s.spec.y) for s in self.s])
            except:
                m = 1
            for f in self.sdss_filters:
                f.set_gobject(m)
                self.vb.addItem(f.gobject)
                self.vb.addItem(f.label)
        else:
            for f in self.sdss_filters:
                self.vb.removeItem(f.gobject)
                self.vb.removeItem(f.label)

    def SDSSPhot(self):
        if 1:
            self.SDSS_phot = SDSSPhotWidget(self)
        else:
            if self.sdss_filters is None:
                self.sdss_filters = [SpectrumFilter(self, f) for f in ['u', 'g', 'r', 'i', 'z']]
            data = self.IGMspec['BOSS_DR12']
            num = len(data['meta']['Z_VI'])
            out = np.zeros([num, 5])
            for i, d in enumerate(data['spec']):
                out[i] = [f.get_value(x=d['wave'], y=d['flux']) for f in self.sdss_filters]
            out = np.insert(out, 0, data['meta']['THING_ID'], axis=1)
            np.savetxt('temp/sdss_photo.dat', out, fmt='%9i %.2f %.2f %.2f %.2f %.2f')

    def makeH2Stack(self, **kwargs): #beta=-0.9, Nmin=16, Nmax=22, norm=0, b=4, load=True, draw=True):
        return makeH2Stack(self, **kwargs)

    def H2StackFit(self, **kwargs):
        H2StackFit(self, **kwargs)

    def makeHIStack(self, **kwargs):
        return makeHIStack(self, **kwargs)

    def HIStackFitPower(self, **kwargs):
        HIStackFitPower(self, **kwargs)

    def HIStackFitGamma(self, load=True, draw=True):
        HIStackFitGamma(self, load=load, draw=draw)
    #>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    #>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    #>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    # >>>
    # >>>   Samples routines
    # >>>
    #>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    #>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    #>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    
    def showXQ100list(self):
        
        if not hasattr(self, 'XQ100data'):
            self.XQ100data = load_QSO()
            dtype = [('id', np.str_, 10), ('z_em', np.float_), ('HighRes', np.str_, 1), ('cont', np.str_, 1),
                    ('DLA', list), ('LLS', list)
                     ]
            x = []
            for i, q in enumerate(self.XQ100data):
                x.append(tuple([getattr(q, a[0]) for a in dtype]))
            #print(x)
            x = np.array(x, dtype=dtype)
            #print(x)
            self.XQ100data = x
            self.statusBar.setText('XQ100 list was loaded')
        if len(self.XQ100data) > 0:
            self.XQ100list = QSOlistTable(self, 'XQ100')
            self.XQ100list.setdata(self.XQ100data)            
    
    def showP94list(self):
        
        if not hasattr(self, 'P94data'):
            from H2_summary import load_P94
            self.P94data = load_P94()
            dtype = [('name', np.str_, 20), ('z_em', np.float_), ('z_dla', np.str_, 9),
                     ('HI', np.float_), ('H2', np.float_), ('Me', np.float_), ('SiII', np.float_),
                     ('SII', np.float_), ('ZnII', np.float_), ('FeII', np.float_)]
            x = []
            for i, q in enumerate(self.P94data):
                row = []
                for a in dtype:
                    if a[0] == 'z_dla':
                        row.append('{:.7f}'.format(q.z_dla))
                    elif a[0] in ['H2', 'HI', 'Me', 'SiII', 'SII', 'ZnII', 'FeII']:
                        row.append(q.e[a[0]].col.val)
                    else:
                        row.append(getattr(q, a[0]))
                print(row)
                x.append(tuple(row))
            #print(x)
            x = np.array(x, dtype=dtype)
            self.P94data = x
            self.statusBar.setText('P94 list was loaded')
        
        if len(self.P94data) > 0:
            self.P94list = QSOlistTable(self, 'P94')
            self.P94list.setdata(self.P94data)

    def showDLAlist(self):

        if not hasattr(self, 'DLAdata'):
            dtype = [('plate', np.int_), ('MJD', np.int_), ('fiber', np.int_),
                     ('z_DLA', np.float_), ('HI', np.float_)]

            self.DLAdata = np.genfromtxt('C:/science/Noterdaeme/GarnettDLAs/DLA22.dat', unpack=True, dtype=dtype)
            self.statusBar.setText('P94 list was loaded')

        if len(self.DLAdata) > 0:
            self.DLAlist = QSOlistTable(self, 'DLA')
            self.DLAlist.setdata(self.DLAdata)

    def showLyalist(self):

        filename = self.options('Lyasamplefile')
        if os.path.isfile(filename):
            with open(filename) as f:
                n = np.min([len(line.split()) for line in f])

            self.Lyadata = np.genfromtxt(filename, names=True, unpack=True, usecols=range(n), delimiter='\t',
                                         dtype = ('U20', 'U20', 'U20', float, float, float, float, float, float, float, float, 'U100'),
                                         )
            self.statusBar.setText('Lya sample was loaded')

        if len(self.Lyadata) > 0:
            self.Lyalist = QSOlistTable(self, 'Lya', folder=os.path.dirname(filename))
            self.Lyalist.setdata(self.Lyadata)

    def showLyalines(self):

        filename = self.options('Lyasamplefile').replace('sample.dat', 'lines.dat')
        if os.path.isfile(filename):
            self.Lyalines = np.genfromtxt(filename, names=True, unpack=True,
                                         dtype = (float, float, float, float, float, float, float, 'U20', 'U30', 'U30'),
                                         )
            self.statusBar.setText('Lya lines data was loaded')

        if len(self.Lyalines) > 0:
            self.Lyalinestable = QSOlistTable(self, 'Lyalines', folder=os.path.dirname(filename))
            mask = np.ones_like(self.Lyalines['t'], dtype=bool)
            #mask = (self.Lyalines['t'] != 'b') * (self.Lyalines['chi'] < 1.3)
            self.Lyalinestable.setdata(self.Lyalines[mask])
            #self.data = add_field(self.Lyalines[mask], [('ind', int)], np.arange(len(self.Lyalines[mask])))

    def showVandels(self):
        data = np.genfromtxt(self.VandelsFile, delimiter=',', names=True,
                             dtype=('U19', '<f8', '<f8', '<f8', 'U12', '<f8', 'U10', '<f8', 'U9', '<i4', '<f8', '<f8', '<f8', '<f8', 'U24', 'U9', 'U9', 'U9', 'U50'))
        self.VandelsTable = QSOlistTable(self, 'Vandels', folder=os.path.dirname(self.VandelsFile))
        self.VandelsTable.setdata(data)

    def showKodiaq(self):
        data = np.genfromtxt(self.KodiaqFile, names=True,
                             dtype=('U17', 'U30', 'U25', 'U14', 'U17', 'U10', 'U15', 'U9', '<f8', '<f8', '<f8', '<i4'))
        self.KodiaqTable = QSOlistTable(self, 'Kodiaq', folder=os.path.dirname(self.KodiaqFile))
        self.KodiaqTable.setdata(data)

    def showUVES(self):
        self.UVESTable = QSOlistTable(self, 'UVES', folder=self.UVESfolder)
        data = np.genfromtxt(self.UVESfolder+'list.dat', names=True, delimiter='\t',
                             dtype=('U20', '<f8', '<f8', '<i4', '<i4', 'U5', 'U20', 'U200'))
        self.UVESTable.setdata(data)

    def showIGMspec(self, cat, data=None):
        self.IGMspecTable = IGMspecTable(self, cat)
        print(cat, data)
        self.IGMspecTable.setdata(data=data)

    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    # >>>
    # >>>   Generation routines
    # >>>
    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    
    def loadSDSSmedian(self):
        self.importSpectrum('data/SDSS/medianQSO.dat', header=2)
        self.z_abs = 0
        self.vb.enableAutoRange()
        self.abs.redraw()
        self.statusBar.setText('median VanDen Berk spectrum is imported')
   
    def loadHSTmedian(self):
        self.importSpectrum('data/SDSS/hst_composite.dat', header=2)
        self.z_abs = 0
        self.vb.enableAutoRange()
        self.abs.redraw()
        self.statusBar.setText('median HST spectrum is imported')
    
    def add_abs_system(self):
        self.generateAbs = GenerateAbsWidget(self)
        
    def add_dust_system(self):
        self.generateAbs = GenerateAbsWidget(self)

    def generate(self, template='current', z=0, fit=True, xmin=3500, xmax=10000, resolution=2000, snr=None,
                 lyaforest=0.0, lycutoff=True, Av=0.0, Av_bump=0.0, z_Av=0.0, redraw=True):
        if template in ['Slesing', 'VanDenBerk', 'HST', 'const']:
            s = Spectrum(self, name='mock')
            if template == 'Slesing':
                data = np.genfromtxt('data/SDSS/Slesing2016.dat', skip_header=0, unpack=True)
                fill_value = 'extrapolate'
            if template == 'VanDenBerk':
                data = np.genfromtxt('data/SDSS/medianQSO.dat', skip_header=2, unpack=True)
                fill_value = (1.3, 0.5)
            elif template == 'HST':
                data = np.genfromtxt('data/SDSS/hst_composite.dat', skip_header=2, unpack=True)
                fill_value = 'extrapolate'
            elif template == 'const':
                data = np.ones((2, 10))
                data[0] = np.linspace(xmin/(1+z), xmax/(1+z), 10)
                fill_value = 1
            data[0] *= (1 + z)
            inter = interp1d(data[0], data[1], bounds_error=False, fill_value=fill_value, assume_sorted=True)
            s.resolution = resolution
            bin = (xmin + xmax) / 2 / resolution / 10
            x = np.linspace(xmin, xmax, (xmax - xmin) / bin)
            #debug(len(x), 'lenx')
            s.set_data([x, inter(x), np.ones_like(x) * 0.1])
            self.s.append(s)
            self.s.ind = len(self.s) - 1
        s = self.s[self.s.ind]
        s.cont.x, s.cont.y = s.spec.raw.x[:], s.spec.raw.y[:]
        s.cont.n = len(s.cont.y)
        s.cont_mask = np.logical_not(np.isnan(s.spec.raw.x))
        s.spec.normalize()

        if lyaforest > 0 or Av > 0 or lycutoff:
            y = s.spec.raw.y
            if lyaforest > 0:
                y *= add_LyaForest(x=s.spec.raw.x, z_em=z, factor=lyaforest)
            if Av > 0:
                y *= add_ext_bump(x=s.spec.raw.x, z_ext=z_Av, Av=Av, Av_bump=Av_bump)
            if lycutoff:
                y *= add_LyaCutoff(x=s.spec.raw.x, z=z)
            s.spec.set(y=y)

        if fit and len(self.fit.sys) > 0:
            s.findFitLines(all=True, debug=False)
            s.calcFit_fft(recalc=True, redraw=False, debug=False)
            s.fit.norm.interpolate(fill_value=1.0)
            s.spec.set(y=s.spec.raw.y * s.fit.norm.inter(s.spec.raw.x))

        if snr is not None:
            s.spec.set(y=s.spec.raw.y + s.cont.y * np.random.normal(0.0, 1.0 / snr, s.spec.raw.n))
            s.spec.set(err=s.cont.y / snr)

        if redraw:
            self.s.redraw()
            self.vb.enableAutoRange()

        if self.SDSS_filters_status:
            m = max([max(self.s[self.s.ind].spec.y())])
            for f in self.sdss_filters:
                f.update(m)

        if self.SDSS_filters_status:
            d = {}
            for f in self.sdss_filters:
                d[f.name] = f.value
            return d

    def colorColorPlot(self):
        self.colorcolor = colorColorWidget(self)

    #>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    #>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    #>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    # >>>
    # >>>   Help program routines
    # >>>
    #>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    #>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    #>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    
    def info_howto(self):
        self.howto = infoWidget(self, 'How to', file='help/howto.txt')
        self.howto.show()
    
    def info_tutorial(self):
        self.tutorial = infoWidget(self, 'Tutorial', file='help/tutorial.txt')
        self.tutorial.show()

    def info_about(self):
        self.about = infoWidget(self, 'About program', file='help/about.txt')
        self.about.show()

    def closeEvent(self, event):
        
        if 0:
            reply = QMessageBox.question(self, 'Message',
                "Are you sure want to quit?", QMessageBox.Yes | 
                QMessageBox.No, QMessageBox.No)
    
            if reply == QMessageBox.Yes:
                event.accept()
            else:
                event.ignore()   
            
if __name__ == '__main__':
    
    app = QApplication(sys.argv)
    #ex = Main()
    sys.exit(app.exec_())
