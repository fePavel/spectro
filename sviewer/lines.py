from astropy import constants as const
from collections import OrderedDict
from functools import partial
from itertools import combinations
from matplotlib import cm
from PyQt5.QtCore import Qt
from PyQt5.QtGui import (QFont)
from PyQt5.QtWidgets import (QWidget, QLabel, QGridLayout, QPushButton,
                             QApplication, QHBoxLayout, QVBoxLayout)
import pyqtgraph as pg
from ..atomic import *
from ..profiles import tau
from .fit import par
from .utils import Timer

class absSystemIndicator():
    def __init__(self, parent):
        self.parent = parent
        self.lines = []
        self.update()

    def add(self, lines, color=(0, 0, 0), va='down'):
        for line in lines:
            if line not in self.linelist:
                l = LineLabel(self, line, self.parent.linelabels, color=color, va=va)
                self.parent.vb.addItem(l)
                self.lines.append(l)
        self.redraw()

    def remove(self, lines=None, el=None):
        if el is None and lines is None:
            lines = self.lines
        if el is not None:
            lines = [l for l in self.lines if str(l.line).startswith(el)]
        if not isinstance(lines, list):
            lines = [lines]
        for line in lines:
            for i in reversed(range(len(self.lines))):
                if line == self.lines[i].line:
                    self.parent.vb.removeItem(self.lines[i])
                    try:
                        self.parent.lines.remove(str(line))
                    except:
                        pass
                    self.lines.pop(i)
                    break
        self.redraw()

    def changeStyle(self):
        lines = self.lines[:]
        for line in lines:
            l, c = line.line, line.color
            self.parent.vb.removeItem(line)
            l = LineLabel(self, l, self.parent.linelabels, color=c)
            self.parent.vb.addItem(l)
            self.lines.append(l)
        self.redraw()

    def update(self):
        self.linelist = [l.line for l in self.lines]
        self.linenames = [str(l.line) for l in self.lines]
        self.activelist = [l for l in self.lines if l.active]

    def index(self, linename):
        if linename in self.linenames:
            return self.linenames.index(linename)
        else:
            return None

    def redraw(self, z=None):
        self.update()
        if z is not None:
            self.parent.z_abs = z
            self.parent.panel.z_panel.setText(str(z))
        if hasattr(self.parent, 's') and len(self.parent.s) > 0:
            for line in self.lines:
                #print(line.line.name, line.active)
                #line.setActive()
                line.redraw(self.parent.z_abs)

    def set_reference(self, line=None):
        if hasattr(self, 'reference'):
            self.reference.set_reference(not self.reference.reference)
        if line is not None:
            if not hasattr(self, 'reference') or self.reference != line:
                self.reference = line
                self.reference.set_reference(True)

class LineLabel(pg.TextItem):
    def __init__(self, parent, line, graphicType, **kwrds):
        self.parent = parent
        self.line = line
        self.saved_color = kwrds['color']
        if 'va' in kwrds:
            self.va = kwrds['va']
            del kwrds['va']
            if self.va == 'down':
                anchor, angle, tailLen, pos = [0.5, -2], 90, 30, (0, 5)
            elif self.va == 'up':
                anchor, angle, tailLen, pos = [0.5, 2], -90, 30, (0, -10)
            pg.TextItem.__init__(self, text='', anchor=anchor, fill=pg.mkBrush(0, 0, 0, 0), **kwrds)
        self.graphicType = graphicType
        self.reference = False
        self.info = False
        self.setPointer()
        font = QFont("SansSerif", 10)
        font.setBold(True)
        font.setWeight(75)
        self.setFont(font)
        self.setActive()

    def setPointer(self):
        if hasattr(self, 'arrow'):
            self.parent.parent.plot.vb.removeItem(self.arrow)
        if self.reference:
            pen = pg.mkPen(color=(180, 190, 30, 255), width=1.5, style=Qt.SolidLine)
        else:
            pen = pg.mkPen(color=self.saved_color, width=.5, style=Qt.SolidLine)
        if self.va == 'down':
            anchor, angle, tailLen, pos = [0.5, -2], 90, 30, (0, 5)
        elif self.va == 'up':
            anchor, angle, tailLen, pos = [0.5, 2], -90, 30, (0, -10)
        if self.graphicType == 'short':
            anchor[0] = anchor[1] - 1 if self.va == 'down' else anchor[1] + 1
            self.arrow = pg.ArrowItem(angle=angle, headWidth=0, headLen=0, tailLen=tailLen, tailWidth=2,
                                      brush=pg.mkBrush(self.saved_color), pen=pg.mkPen(0, 0, 0, 0), pos=pos)
        elif self.graphicType == 'infinite':
            self.arrow = pg.InfiniteLine(angle=90, pen=pen, label='') #style=Qt.DashLine
        self.arrow.setParentItem(self)

    def setActive(self, bool=None):
        if bool is not None:
            self.active = bool
        else:
            self.active = True if str(self.line) in self.parent.parent.lines else False

        if self.info:
            text = str(self.line)
            text += ', l={:.3f}, f={:.4f}, g={:.2E}'.format(self.line.l(), self.line.f(), self.line.g())
            if self.line.name in self.parent.parent.fit.sys[self.parent.parent.comp].sp.keys():
                self.line.logN = self.parent.parent.fit.sys[self.parent.parent.comp].sp[self.line.name].N.val
                self.line.b = self.parent.parent.fit.sys[self.parent.parent.comp].sp[self.line.name].b.val
                t = tau(line=self.line)
                text += ', logN={: .2f}, b={: .2f}, tau_0={:.2f}'.format(self.line.logN, self.line.b, t.calctau0())
            self.setText(text)
        else:
            if self.parent.parent.show_osc:
                self.setText(str(self.line)+' {:.4f}'.format(self.line.f()))
            else:
                self.setText(str(self.line))

        if self.active:
            self.color = (255, 255, 255)
            self.fill = pg.mkBrush(85, 130, 20, 255)
            self.zvalue = 11
        else:
            self.color = self.saved_color
            self.fill = pg.mkBrush(0, 0, 0, 0, width=0)
            self.zvalue = 10

        if self.reference:
            self.color = (255, 255, 0)
            self.zvalue = 11

        if self.info:
            self.color = (255, 255, 200)
            self.zvalue = 11

        self.border = pg.mkPen(color=self.color + (0,), width=self.active + self.reference)
        self.setColor(pg.mkColor(*self.color))
        self.setZValue(self.zvalue)

        #self.paint()

    def set_reference(self, bool):
        self.reference = bool
        if self.reference:
            self.graphicType = 'infinite'
        else:
            self.graphicType = self.parent.parent.linelabels
        self.setPointer()
        self.setActive()

    def redraw(self, z):
        if len(self.parent.parent.s) > 0:
            ypos = self.parent.parent.s[self.parent.parent.s.ind].spec.inter(self.line.l() * (1 + z))
            if ypos == 0:
                for s in self.parent.parent.s:
                    ypos = s.spec.inter(self.line.l() * (1 + z))
                    if ypos != 0:
                        break
        else:
            ypos = self.parent.parent.vb.mapSceneToView(self.scenePos()).y()
        self.setPos(self.line.l() * (1 + z), ypos)
        return self.line.l() * (1 + z), ypos

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
            self.parent.parent.z_abs += (pos.x() - self.st_pos) / self.line.l()
            self.parent.parent.panel.refresh()
            #self.parent.parent.line_reper = self.line
            self.parent.parent.plot.updateVelocityAxis()
            self.parent.redraw()
            ev.accept()

        elif QApplication.keyboardModifiers() == Qt.AltModifier or self.info:
            self.showInfo()
            ev.accept()
    #def hoverEvent(self, ev):
    #    if ev.isEnter():
    #        print(ev.pos())
    #        print('hover', self.line.name)
    #    #ev.ignore()


    def mouseClickEvent(self, ev):

        if ev.double():
            self.setActive(not self.active)
            if self.active and str(self.line) not in self.parent.parent.lines:
                self.parent.parent.lines.add(str(self.line) + ' exp_' + str(self.parent.parent.s.ind))
            if not self.active:
                self.parent.parent.lines.remove(str(self.line))
            ev.accept()
        else:
            if QApplication.keyboardModifiers() == Qt.ShiftModifier:
                self.parent.set_reference(self)
                self.parent.parent.plot.restframe = False
                self.parent.parent.plot.updateVelocityAxis()

                ev.accept()
            elif QApplication.keyboardModifiers() == Qt.ControlModifier:
                self.parent.remove(self.line)
                del self
            elif QApplication.keyboardModifiers() == Qt.AltModifier or self.info:
                self.showInfo()
                ev.accept()

    def showInfo(self, show=None):
        if show is not None:
            self.info = show
        else:
            for l in self.parent.lines:
                if l.info and l is not self:
                    l.showInfo(show=False)
            self.info = not self.info

        self.setActive(self.active)


    def clicked(self, pts):
        print("clicked: %s" % pts)

    def __hash__(self):
        return hash(str(self.line.l()) + str(self.line.f()))

    def __eq__(self, other):
        if self.line == other:
            return True
        else:
            return False

class lineList(list):
    def __init__(self, parent):
        super(lineList).__init__()
        self.parent = parent
        #' '.join(l.split()[0:2])

    def check(self, line):
        if line in self:
            for i, l in enumerate(self):
                if line == ' '.join(l.split()[:2]):
                    return i
            else:
                return None
        else:
            return None

    def add(self, line=None):
        if line is not None and self.check(line) is None:
            self.append(line)
            self.setActive(line, True)

    def remove(self, line):
        i = self.check(line)
        print(i)
        if i is not None:
            self.setActive(line, False)
            del self[i]

    def setActive(self, line, active=False):
        if self.parent.abs.index(' '.join(line.split()[0:2])) is not None:
            self.parent.abs.lines[self.parent.abs.index(' '.join(line.split()[0:2]))].setActive(active)

    def fromText(self, text):
        for i in reversed(range(len(self))):
            self.remove(self[i])
        for line in text.splitlines():
            self.add(line)

    def __contains__(self, item):
        return any(item == ' '.join(x.split()[:2]) for x in self)

    def __str__(self):
        return '\n'.join([str(l) for l in self])

class choiceLinesWidget(QWidget):
    def __init__(self, parent, d):
        super().__init__()
        self.parent = parent
        self.d = d
        self.resize(1700, 1200)
        self.move(400, 100)
        self.setStyleSheet(open('config/styles.ini').read())
        layout = QVBoxLayout()
        self.grid = QGridLayout()
        layout.addLayout(self.grid)

        self.grid.addWidget(QLabel('HI:'), 0, 0)

        self.showAll = QPushButton("Show all")
        self.showAll.setFixedSize(100, 30)
        self.showAll.clicked[bool].connect(partial(self.showLines, 'all'))
        self.hideAll = QPushButton("HIde all")
        self.hideAll.setFixedSize(100, 30)
        self.hideAll.clicked[bool].connect(partial(self.showLines, 'none'))
        self.okButton = QPushButton("Ok")
        self.okButton.setFixedSize(100, 30)
        self.okButton.clicked[bool].connect(self.close)
        hbox = QHBoxLayout()

        hbox.addWidget(self.showAll)
        hbox.addWidget(self.hideAll)
        hbox.addStretch(1)
        hbox.addWidget(self.okButton)

        layout.addLayout(hbox)
        self.setLayout(layout)

    def addItems(self, parent):
        for s in self.d.items():
            self.par_item = self.addParent(parent, s[0], expanded=True)
            if len(s[1]) > 1:
                for c in s[1]:
                    self.addChild(self.par_item, 1, c.replace('=', ''), c, 2)

    def showLines(self, lines):

        pass
        # self.close()

        # self.close()

class doubletList(list):
    def __init__(self, parent):
        super(doubletList).__init__()
        self.parent = parent

    def append(self, obj):
        super(doubletList, self).append(obj)
        self.update()

    def update(self):
        for i, doublet in enumerate(self):
            doublet.redraw(pen=pg.mkPen(cm.terrain(0.1 + 0.9 * i / len(self), bytes=True)[:3] + (200,)))

    def fromText(self, text):
        for i in reversed(range(len(self))):
            self.remove(str(self[i]))
        for reg in text.splitlines():
            self.add(reg)

    def __str__(self):
        return '\n'.join([str(r) for r in self])

class Doublet():
    def __init__(self, parent, name=None, z=None, color=pg.mkColor(45, 217, 207)):
        self.parent = parent
        self.read()
        self.active = False
        color = cm.terrain(1, bytes=True)[:3] + (200,)
        self.pen = pg.mkPen(color=color, width=0.5, style=Qt.SolidLine)
        self.name = name
        self.z = z
        self.temp = None
        if self.name is not None and self.z is not None:
            self.draw(add=False)

    def read(self):
        self.doublet = {}
        with open('data/doublet.dat') as f:
            for line in f:
                if '#' not in line:
                    self.doublet[line.split()[0]] = [float(d) for d in line.split()[1:]]

    def draw(self, add=True):
        self.l = self.doublet[self.name]
        self.line, self.label = [], []
        for l in self.l:
            self.line.append(pg.InfiniteLine(l * (1 + self.z), angle=90, pen=self.pen))
            self.parent.vb.addItem(self.line[-1])
            anchor = (0, 1) if 'DLA' not in self.name else (0, 0)
            self.label.append(doubletLabel(self, self.name, l, angle=90, anchor=anchor))
            self.parent.vb.addItem(self.label[-1])
        if add and self.name.strip() in ['CIV', 'SiIV', 'AlIII', 'FeII', 'MgII']:
            self.parent.doublets.append(Doublet(self.parent, name='DLA', z=self.z))

    def redraw(self, pen=None):
        #self.determineY()
        if hasattr(self, 'l'):
            if self.active:
                self.pen = pg.mkPen(225, 215, 0, width=2)
            else:
                if pen is None:
                    self.pen = pg.mkPen(45, 217, 207, width=0.5)
                else:
                    self.pen = pen
            for l, line, label in zip(self.l, self.line, self.label):
                line.setPos(l * (1 + self.z))
                line.setPen(self.pen)
                label.redraw()

    def remove(self):
        if self.temp is not None:
            self.remove_temp()
        else:
            for line, label in zip(self.line, self.label):
                self.parent.vb.removeItem(line)
                self.parent.vb.removeItem(label)
            self.parent.doublets.remove(self)

        self.parent.doublets.update()
        del self

    def draw_temp(self, x):
        self.line_temp = pg.InfiniteLine(x, angle=90, pen=pg.mkPen(color=(44, 160, 44), width=2, style=Qt.SolidLine))
        self.parent.vb.addItem(self.line_temp)
        self.temp = []
        for lines in self.doublet.values():
            for d in combinations(lines, 2):
                for i in [-1, 1]:
                    x = self.line_temp.value() * (d[0] / d[1])**i
                    self.temp.append(doubletTempLine(self, x, angle=90, pen=pg.mkPen(color=(160, 80, 44), width=1, style=Qt.SolidLine)))
                    self.parent.vb.addItem(self.temp[-1])

    def remove_temp(self):
        if self.temp is not None:
            self.parent.vb.removeItem(self.line_temp)
            for t in self.temp:
                self.parent.vb.removeItem(t)
        self.temp = None

    def determineY(self):
        s = self.parent.parent.s[self.parent.parent.s.ind]
        imin, imax = s.spec.index([self.l1*(1+self.z), self.l2*(1+self.z)])[:]
        imin, imax = max(0, int(imin - (imax-imin)/2)), min(int(imax + (imax-imin)/2), s.spec.n())
        self.y = np.median(s.spec.y()[imin:imax])*1.5

    def set_active(self, active=True):
        if active:
            for d in self.parent.doublets:
                print(d.name, d.z)
                d.set_active(False)
        self.active = active
        self.parent.parent.setz_abs(self.z)
        #self.redraw()

    def find(self, x1, x2, toll=9e-2, show=True):
        """
        Function which found most appropriate doublet using two wavelengths.
        parameters:
            - x1        :  first wavelength
            - x2        :  second wavelength
            - toll      :  tollerance for relative position

        """
        x1, x2 = np.min([x1, x2]), np.max([x1, x2])
        diff = 1-x1/x2

        res, ind = [], []
        for k, v in self.doublet.items():
            for d in combinations(v, 2):
                if -toll < 1 - (diff / (1 - d[0] / d[1])) < toll:
                    res.append(1- (diff / (1- d[0]/d[1])))
                    ind.append((k, d[0]))
        if show:
            self.remove_temp()

        if len(res) > 0:
            i = np.argmin(np.abs(res))
            self.name = ind[i][0] #.decode('UTF-8').replace('_', '')
            self.z = x1 / ind[i][1] - 1
            if show:
                self.parent.parent.console.exec_command('show '+self.name)
                self.parent.parent.setz_abs(self.z)
                self.draw()
            else:
                return self.name, self.z
        else:
            self.parent.doublets.remove(self)
            del self

class doubletTempLine(pg.InfiniteLine):
    def __init__(self, parent, x, **kwargs):
        super().__init__(x, **kwargs)
        self.parent = parent
        self.x = x

    def setMouseHover(self, hover):
        super().setMouseHover(hover)
        if self.parent.temp is not None:
            name, z = self.parent.find(self.x, self.parent.line_temp.getXPos(), show=False)
            anchor = (0, 1) if 'DLA' not in name else (0, 0)
            self.parent.temp.append(doubletLabel(self.parent, name + '_' + str(int(self.parent.line_temp.getXPos()/(1+z))), self.x/(1+z), angle=90, anchor=anchor, temp=True))
            self.parent.parent.vb.addItem(self.parent.temp[-1])

class doubletLabel(pg.TextItem):
    def __init__(self, parent, name, line, temp=False, **kwrds):
        self.parent = parent
        self.name = name
        self.line = line
        self.temp = temp
        pg.TextItem.__init__(self, text=self.name, fill=pg.mkBrush(0, 0, 0, 0), **kwrds)
        self.setFont(QFont("SansSerif", 8))
        self.determineY()
        self.redraw()

    def determineY(self):
        s = self.parent.parent.parent.s[self.parent.parent.parent.s.ind]
        imin, imax = s.spec.index([self.line * (1 + self.parent.z) * (1 - 0.001), self.line * (1 + self.parent.z) * (1 + 0.001)])[:]
        imin, imax = max(0, int(imin - (imax - imin) / 2)), min(int(imax + (imax - imin) / 2), s.spec.n())
        if imin < imax:
            self.y = np.median(s.spec.y()[imin:imax]) * 1.5
        else:
            self.y = s.spec.y()[imin-1] * 1.5

    def redraw(self):
        self.determineY()
        self.setText(self.name + ' ' + str(self.line)[:str(self.line).index('.')] + '   z=' + str(self.parent.z)[:6])
        if self.temp:
            self.setColor((200,200,200))
        else:
            self.setColor(self.parent.pen.color())
        self.setPos(self.line * (1 + self.parent.z), self.y)

    def mouseDragEvent(self, ev):

        if QApplication.keyboardModifiers() == Qt.ShiftModifier:
            if ev.button() != Qt.LeftButton:
                ev.ignore()
                return

            pos = self.getViewBox().mapSceneToView(ev.scenePos())
            if not ev.isStart():
                self.parent.z += (pos.x() - self.st_pos) / self.line
            self.st_pos = pos.x()
            self.parent.redraw()
            ev.accept()

    def mouseClickEvent(self, ev):

        if QApplication.keyboardModifiers() == Qt.ControlModifier:
            self.parent.remove()
            ev.accept()

        if ev.double():
            print(self.parent.active)
            self.parent.set_active(not self.parent.active)
            self.parent.parent.doublets.update()

    def clicked(self, pts):
        print("clicked: %s" % pts)

class pcRegion():
    def __init__(self, parent, ind, x1=None, x2=None):
        self.parent = parent
        self.setInd(ind)
        self.color = pg.mkColor(220, 20, 60)
        if x1 is not None and x2 is not None:
            if isinstance(x1, float) and isinstance(x2, float):
                self.x1, self.x2 = x1, x2
                self.value = 0.1
            else:
                self.x1, self.x2 = np.min([x1.x(), x2.x()]), np.max([x1.x(), x2.x()])
                self.value = (x1.y() + x2.y()) / 2
        else:
            self.x1, self.x2 = 3000, 9000
            self.value = 0.0
        self.draw()
        if not self.parent.parent.fit.cf_fit:
            self.parent.parent.fit.cf_fit = True
        try:
            self.parent.parent.fitModel.cf.setExpanded(self.parent.parent.fit.cf_fit)
            self.parent.parent.fitModel.addChild('cf', 'cf_' + str(ind))
        except:
            pass
        self.parent.parent.fit.cf_num += 1
        if x1 is not None and x2 is not None:
            self.parent.parent.fit.add('cf_' + str(self.parent.parent.fit.cf_num-1))
            self.updateFitModel()


    def draw(self):
        self.gline = pg.PlotCurveItem(x=[self.x1, self.x2], y=[self.value, self.value], pen=pg.mkPen(color=self.color), clickable=True)
        self.gline.sigClicked.connect(self.lineClicked)
        self.parent.vb.addItem(self.gline)
        self.label = cfLabel(self, color=self.color)
        self.parent.vb.addItem(self.label)

    def redraw(self):
        self.gline.setData(x=[self.x1, self.x2], y=[self.value, self.value])
        self.label.redraw()

    def setInd(self, ind):
        self.ind = ind
        self.name = 'cf_' + str(ind)
        self.labelname = 'LFR ' + str(ind)

    def updateFromFit(self):
        self.value = 1 - getattr(self.parent.parent.fit, self.name).val
        self.x1 = getattr(self.parent.parent.fit, self.name).min
        self.x2 = getattr(self.parent.parent.fit, self.name).max
        self.redraw()

    def updateFitModel(self):
        #print(self.name, self.value, self.x1, self.x2)
        self.parent.parent.fit.setValue(self.name, 1-self.value)
        self.parent.parent.fit.setValue(self.name, self.x1, 'min')
        self.parent.parent.fit.setValue(self.name, self.x2, 'max')
        try:
            self.parent.parent.fitModel.refresh()
        except:
            pass

    def remove(self):
        self.parent.vb.removeItem(self.gline)
        self.parent.vb.removeItem(self.label)
        self.parent.pcRegions.remove(self)
        try:
            for i in range(self.ind, len(self.parent.pcRegions) + 1):
                self.parent.parent.fitModel.cf.removeChild(getattr(self.parent.parent.fitModel, 'cf_' + str(i)))
        except:
            pass

        if self.ind < len(self.parent.pcRegions):
            for i in range(self.ind, len(self.parent.pcRegions)):
                print(i)
                self.parent.pcRegions[i].setInd(i)
                cf = getattr(self.parent.parent.fit, 'cf_' + str(i + 1))
                setattr(self.parent.parent.fit, 'cf_' + str(i), par(self, 'cf_' + str(i), cf.val, cf.min, cf.max, cf.step, addinfo=cf.addinfo))
                self.parent.pcRegions[i].redraw()

        self.parent.parent.fit.remove('cf_' + str(len(self.parent.pcRegions)))
        self.parent.parent.fit.cf_num = len(self.parent.pcRegions)
        if self.parent.parent.fit.cf_num == 0:
            self.parent.parent.fit.cf_fit = False

        try:
            if self.ind < len(self.parent.pcRegions):
                for i in range(self.ind, len(self.parent.pcRegions)):
                    self.parent.parent.fitModel.addChild('cf', 'cf_' + str(i))

            self.parent.parent.fitModel.refresh()
        except:
            pass

        del self

    def lineClicked(self):
        if QApplication.keyboardModifiers() == Qt.ControlModifier:
            self.remove()

class cfLabel(pg.TextItem):
    def __init__(self, parent,  **kwrds):
        self.parent = parent
        pg.TextItem.__init__(self, text=self.parent.labelname, anchor=(0, 1), fill=pg.mkBrush(0, 0, 0, 0), **kwrds)
        self.setFont(QFont("SansSerif", 12))
        self.redraw()

    def redraw(self):
        self.setText(self.parent.labelname)
        self.setPos(self.parent.x1 + (self.parent.x2 - self.parent.x1)*0.1, self.parent.value)

    def mouseDragEvent(self, ev):

        if QApplication.keyboardModifiers() == Qt.ShiftModifier:
            if ev.button() != Qt.LeftButton:
                ev.ignore()
                return

            pos = self.parent.parent.parent.vb.mapSceneToView(ev.pos())
            if ev.isStart():
                # We are already one step into the drag.
                # Find the point(s) at the mouse cursor when the button was first
                # pressed:
                self.st_pos = pos
            self.parent.x1 += (pos.x() - self.st_pos.x())
            self.parent.x2 += (pos.x() - self.st_pos.x())
            self.parent.value += (pos.y() - self.st_pos.y())
            self.parent.updateFitModel()
            self.parent.redraw()
            ev.accept()

    def mouseClickEvent(self, ev):

        if QApplication.keyboardModifiers() == Qt.ControlModifier:
            self.parent.remove()
            ev.accept()

    def clicked(self, pts):
        print("clicked: %s" % pts)