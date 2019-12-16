from copy import copy
from collections import OrderedDict
import gc
import numpy as np
from .utils import Timer
from ..a_unc import a
from ..atomic import abundance, doppler
from ..pyratio import pyratio

class par:
    def __init__(self, parent, name, val, min, max, step, addinfo='', vary=True, fit=True, show=True):
        self.parent = parent
        self.name = name
        if 'cont' in self.name:
            self.dec = 4
        elif 'res' in self.name:
            self.dec = 1
        elif 'cf' in self.name:
            self.dec = 3
        elif 'dispz' in self.name:
            self.dec = 1
        elif 'disps' in self.name:
            self.dec = 8
        else:
            d = {'z': 7, 'b': 3, 'N': 3, 'turb': 3, 'kin': 2, 'mu': 8, 'dtoh': 3, 'me': 3,
                 'Ntot': 3, 'logn': 3, 'logT': 3, 'logf': 3, 'rad': 3}
            self.dec = d[self.name]

        if self.name in ['N', 'Ntot', 'logn', 'logT', 'rad', 'dtoh', 'me', 'mu']:
            self.form = 'l'
        else:
            self.form = 'd'

        if self.name in ['b', 'N']:
            self.sys = self.parent.parent
        elif self.name in ['z', 'turb', 'kin', 'Ntot', 'logn', 'logT', 'logf', 'rad']:
            self.sys = self.parent
        else:
            self.sys = None
        self.val = val
        self.min = min
        self.max = max
        self.step = step
        self.vary = vary
        self.addinfo = addinfo
        self.fit = fit
        self.fit_w = self.fit
        self.show = show
        self.unc = a()

    def set(self, val, attr='val'):
        if attr == 'unc':
            if isinstance(val, (int, float)):
                setattr(self, attr, a(self.val, val, self.form))
            elif isinstance(val, str):
                setattr(self, attr, a(val, self.form))
            else:
                setattr(self, attr, val)
        else:
            setattr(self, attr, val)
        if attr == 'val':
            return self.check_range()

    def check_range(self):
        if 'cf' not in self.name:
            min, max = self.min, self.max
        else:
            min, max = 0, 1

        if self.val < min:
            self.val = min
            return False

        if self.val > max:
            self.val = max
            return False

        return True

    def check(self):
        if self.addinfo == '':
            self.vary = True
        else:
            self.vary = False

    def duplicate(self, other):
        attrs = ['val', 'min', 'max', 'step', 'vary', 'addinfo', 'fit', 'fit_w']
        for attr in attrs:
            setattr(self, attr, getattr(other, attr))

    def latexname(self):
        pass

    def ref(self, val=None, attr='val'):
        # special function for lmfit to translate redshift to velocity space
        if self.name.startswith('z'):
            c = 299792.458
            if 1:
                if val is None:
                    self.saved = self.val
                    return c * (self.val - self.saved), c * (self.min - self.saved), c * (self.max - self.saved)
                else:
                    if attr in ['val', 'min', 'max']:
                        return self.saved + val / c
                    elif attr in ['step', 'unc']:
                        return val / c
            else:
                if val is None:
                    self.saved = self.val
                    return self.val / self.saved, self.min / self.saved, self.max / self.saved
                else:
                    if attr in ['val', 'min', 'max']:
                        return val * self.saved
                    elif attr in ['step', 'unc']:
                        return val * self.saved
        else:
            if val is None:
                return self.val, self.min, self.max
            else:
                return val

    def __repr__(self):
        s = self.name
        if self.name in ['z', 'b', 'N', 'turb', 'kin', 'Ntot', 'logn', 'logT', 'logf', 'rad']:
            s += '_' + str(self.sys.ind)
        if self.name in ['b', 'N']:
            s += '_' + self.parent.name
        return s

    def __str__(self):
        s = self.name
        if self.name in ['z', 'b', 'N', 'turb', 'kin', 'Ntot', 'logn', 'logT', 'logf', 'rad']:
            s += '_' + str(self.sys.ind)
        if self.name in ['b', 'N']:
            s += '_' + self.parent.name
        return s

    def str(self, attr=None):
        if attr is None:
            return '{1:} {2:.{0}f} {3:.{0}f} {4:.{0}f} {5:.{0}f} {6:1d} {7:s}'.format(self.dec, self, self.val, self.min, self.max, self.step, self.vary, self.addinfo)
        else:
            return '{0:.{1}f}'.format(getattr(self, attr), self.dec)

    def fitres(self, latex=False, dec=None, showname=True, classview=False, aview=False):
        if self.unc is not None:
            if dec is None:
                d = np.asarray([self.unc.plus, self.unc.minus])
                if len(np.nonzero(d)[0]) > 0:
                    dec = int(np.round(np.abs(np.log10(np.min(d[np.nonzero(d)])))) + 1)
                else:
                    dec = self.dec
            if latex:
                if self.name in ['z']:
                    return '${0:.{3}f}(^{{+{1:d}}}_{{-{2:d}}})$'.format(self.unc.val, int(self.unc.plus*10**dec), int(self.unc.minus*10**dec), dec)
                else:
                    return '${0:.{3}f}^{{+{1:.{3}f}}}_{{-{2:.{3}f}}}$'.format(self.unc.val, self.unc.plus, self.unc.minus, dec)
            elif classview:
                if self.name in ['z']:
                    return 'co = sy({0:.{2}f}, {1:d})'.format(self.unc.val, int(np.sqrt(self.unc.plus**2 + self.unc.minus**2) * 10 ** dec), dec)
                elif self.name in ['N']:
                    return "co.el('{0}', {1:.{4}f}, {2:.{4}f}, {3:.{4}f})".format(self.parent.name, self.unc.val, self.unc.plus, self.unc.minus, dec)
            elif aview:
                return '({0:.{3}f}, {1:.{3}f}, {2:.{3}f})'.format(self.unc.val, self.unc.plus, self.unc.minus, dec)
            else:
                return '{0} = {1:.{4}f} + {2:.{4}f} - {3:.{4}f}'.format(str(self), self.unc.val, self.unc.plus, self.unc.minus, dec)
        else:
            if dec is None:
                dec = self.dec
            if showname:
                return '{0} = {1:.{2}f}'.format(str(self), self.val, dec)
            else:
                return '{0:.{1}f}'.format(self.val, dec)

class fitSpecies:
    def __init__(self, parent, name=None):
        self.parent = parent
        self.name = name
        #self.mass = self.setmass(name)
        self.b = par(self, 'b', 4, 0.5, 200, 0.05)
        self.N = par(self, 'N', 14, 10, 22, 0.01)

    def duplicate(self, other):
        attrs = ['b', 'N']
        for attr in attrs:
            getattr(self, attr).duplicate(getattr(other, attr))

class fitSystem:
    def __init__(self, parent, z=0.0):
        self.parent = parent
        self.z = par(self, 'z', z, z-0.001, z+0.001, 1e-7)
        #self.cons_vary = False
        #self.turb = par(self, 'turb', 5, 0.5, 20, 0.05, vary=self.cons_vary, fit=self.cons_vary)
        #self.kin = par(self, 'kin', 5e4, 1e4, 1e5, 1e3, vary=self.cons_vary, fit=self.cons_vary)
        self.sp = OrderedDict()
        self.total = OrderedDict()
        self.pr = None

    def add(self, name):
        if name in 'turb':
            self.turb = par(self, 'turb', 5, 0.5, 20, 0.05)
        if name in 'kin':
            self.kin = par(self, 'kin', 5e3, 1e3, 3e4, 1e3)
        if name in 'Ntot':
            self.Ntot = par(self, 'Ntot', 14, 12, 22, 0.05)
        if name in 'logn':
            self.logn = par(self, 'logn', 2, -2, 5, 0.05)
        if name in 'logT':
            self.logT = par(self, 'logT', 2, 0.5, 5, 0.05)
        if name in 'logf':
            self.logf = par(self, 'logf', 0, -6, 0, 0.05)
        if name in 'rad':
            self.rad = par(self, 'rad', 0, -6, 6, 0.05)

    def remove(self, name):
        if name in ['turb', 'kin', 'Ntot', 'logn', 'logT', 'logf', 'rad']:
            if hasattr(self, name):
                delattr(self, name)

    def addSpecies(self, name, dic='sp'):
        if name not in getattr(self, dic).keys():
            getattr(self, dic)[name] = fitSpecies(self, name)
            #if self.parent.parent is not None:
            #    self.parent.parent.console.exec_command('show ' + name)
            return True
        else:
            return False

    def duplicate(self, other):
        self.z.duplicate(other.z)
        attrs = ['turb', 'kin', 'Ntot', 'logn', 'logT', 'logf', 'rad']
        for attr in attrs:
            if hasattr(other, attr):
                self.add(attr)
                getattr(self, attr).duplicate(getattr(other, attr))
        self.sp = OrderedDict()
        for k, v in other.sp.items():
            self.sp[k] = fitSpecies(self, name=k)
            self.sp[k].duplicate(v)

    def zshift(self, v):
        self.z.val += float(v) / 299792.458 * (1 + self.z.val)

    def zrange(self, v):
        self.z.min = self.z.val - abs(float(v)) / 299792.458 * (1 + self.z.val)
        self.z.max = self.z.val + abs(float(v)) / 299792.458 * (1 + self.z.val)

    def N(self, sp):
        if sp in self.sp.keys():
            if hasattr(self.parent, 'me') and 'HI' != sp and 'HI' in self.sp.keys():
                return abundance(sp, self.sp['HI'].N.val, self.parent.me.val)
            else:
                return self.sp[sp].N.val

    def pyratio(self, init=False):
        #t = Timer('pyratio '+ str(self.parent.sys.index(self)))
        if init or self.pr is None:
            self.pr = pyratio(z=self.z.val, pumping='simple', radiation='simple', sed_type=self.rad.addinfo)
            #print('init', self.pr.pumping, self.pr.radiation,  self.pr.sed_type)
            d = {'CO': [-1, 10], 'CI': [-1, 3], 'FeII': [-1, 13]}
            for s in self.sp.keys():
                if 'CO' in s:
                    d['CO'][0] = 0 if s[3:4].strip() == '' else max(d['CO'][0], int(s[3:4]))
                    pars = ['T', 'n', 'f', 'rad']
                if 'CI' in s:
                    d['CO'][0] = 0 if s[3:4].strip() == '' else max(d['CO'][0], int(s[3:4]))
                    pars = ['T', 'n', 'f', 'rad']
                if 'FeII' in s:
                    d['FeII'][0] = 0 if s[5:6].strip() == '' else max(d['FeII'][0], int(s[5:6]))
                    pars = ['T', 'e', 'rad']
            self.pr.set_pars(pars)
            for k, v in d.items():
                if v[0] > -1:
                    self.pr.add_spec(k, num=v[1])
            #self.pr.set_prior('f', 0)

        #t.time('init')
        if self.pr is not None:
            self.pr.pars['T'].value = self.logT.val
            if 'n' in self.pr.pars.keys():
                self.pr.pars['n'].value = self.logn.val
            if 'e' in self.pr.pars.keys():
                self.pr.pars['e'].value = self.logn.val
            if 'f' in self.pr.pars.keys():
                self.pr.pars['f'].value = self.logf.val
            if 'rad' in self.pr.pars.keys():
                self.pr.pars['rad'].value = self.rad.val
            for k in self.pr.species.keys():
                col = self.pr.predict(name=k, level=-1, logN=self.Ntot.val)
                for s in self.sp.keys():
                    if k in s and 'Ntot' in self.sp[s].N.addinfo:
                        self.sp[s].N.val = col[self.pr.species[k].names.index(s)]
            #t.time('predict')

    def __str__(self):
        return '{:.6f} '.format(self.z.val) + str(self.sp)

class fitPars:
    def __init__(self, parent):
        self.parent = parent
        self.sys = []
        self.total = fitSystem(self)
        self.total.ind = 'total'
        self.cont_fit = False
        self.cont_num = 0
        self.cont_left = 3500
        self.cont_right = 4000
        self.res_fit = False
        self.res_num = 0
        self.cf_fit = False
        self.cf_num = 0
        self.disp_fit = False
        self.disp_num = 0
        self.tieds = {}

    def add(self, name):
        if name in 'mu':
            self.mu = par(self, 'mu', 1e-6, 1e-7, 5e-6, 1e-8)
        if name in 'me':
            self.me = par(self, 'me', 0, -3, 1, 0.01)
        if name in 'dtoh':
            self.dtoh = par(self, 'dtoh', -4.5, -5.4, -4, 0.01)
        if 'res' in name:
            setattr(self, name, par(self, name, 45000, 1000, 60000, 1, addinfo='exp_0'))
        if 'cont' in name:
            if name == 'cont_0':
                setattr(self, name, par(self, name, 1, 0, 2, 0.01))
            else:
                setattr(self, name, par(self, name, 0, -0.5, 0.5, 0.01))
        if 'cf' in name:
            setattr(self, name, par(self, name, 0.1, 3000, 9000, 0.01, addinfo='all'))
        if 'dispz' in name:
            setattr(self, name, par(self, name, 5000, 3000, 9000, 0.1, addinfo='exp_0'))
        if 'disps' in name:
            setattr(self, name, par(self, name, 1e-5, -1e-4, 1e-4, 1e-6, addinfo='exp_0'))

    def remove(self, name):
        if name in ['mu', 'me', 'dtoh', 'res'] or any([x in name for x in ['cont', 'res', 'cf', 'disp']]):
            if hasattr(self, name):
                delattr(self, name)
                #gc.collect()

    def addTieds(self, p1, p2):
        try:
            self.getPar(p1)
            self.getPar(p2)
            if not (p1 in self.tieds.keys() and self.tieds[p1] == p2):
                self.tieds[p1] = p2
                self.setValue(p1, False, 'vary')
        except:
            pass

    def addSys(self, ind=-1, z=None):
        if z is None:
            if len(self.sys) > 0:
                self.sys.append(fitSystem(self, 0))
                self.sys[-1].duplicate(self.sys[ind])
            else:
                self.sys.append(fitSystem(self, 0))
        else:
            self.sys.append(fitSystem(self, z))
        self.refreshSys()

    def delSys(self, ind=-1):
        s = self.sys[ind]
        self.sys.remove(s)
        del s
        gc.collect()
        self.refreshSys()

    def swapSys(self, i1, i2):
        if self.cf_fit:
            for i in range(self.cf_num):
                if hasattr(self, 'cf_' + str(i)):
                    p = getattr(self, 'cf_' + str(i))
                    cf = p.addinfo.split('_')
                    if cf[0].find('sys') > -1:
                        if i1 in [int(s) for s in cf[0].split('sys')[1:]]:
                            self.setValue('cf_' + str(i), 'sys'.join([s if int(s) != i1 else str(i2) for s in cf[0].split('sys')[1:]])+'_'+cf[1], 'addinfo')
                        if i2 in [int(s) for s in cf[0].split('sys')[1:]]:
                            self.setValue('cf_' + str(i), 'sys'.join([s if int(s) != i2 else str(i1) for s in cf[0].split('sys')[1:]]) + '_' + cf[1], 'addinfo')
                        #if int(p.addinfo[p.addinfo.find('sys')+3:p.addinfo.find('_')]) == i1:
                        #    p.addinfo = p.addinfo[:p.addinfo.find('sys')+3]+str(i2)+p.addinfo[p.addinfo.find('_'):]
                        #elif int(p.addinfo[p.addinfo.find('sys')+3:p.addinfo.find('_')]) == i2:
                        #    p.addinfo = p.addinfo[:p.addinfo.find('sys')+3]+str(i1)+p.addinfo[p.addinfo.find('_'):]
        self.sys[i1], self.sys[i2] = self.sys[i2], self.sys[i1]
        self.refreshSys()

    def refreshSys(self):
        for i, s, in enumerate(self.sys):
            s.ind = i

    def setValue(self, name, val, attr='val'):
        s = name.split('_')
        if attr in ['val', 'min', 'max', 'step']:
            val = float(val)
        elif attr in ['vary', 'fit']:
            val = int(val)

        if s[0] in ['mu', 'me', 'dtoh']:
            if not hasattr(self, s[0]):
                self.add(s[0])
            res = getattr(self, s[0]).set(val, attr)

        if s[0] in ['cont', 'res', 'cf', 'dispz', 'disps']:
            if not hasattr(self, name):
                self.add(name)
            res = getattr(self, name).set(val, attr)

        if s[0] in ['z', 'turb', 'kin', 'Ntot', 'logn', 'logT', 'logf', 'rad']:
            while len(self.sys) <= int(s[1]):
                self.addSys()
            if s[0] in ['turb', 'kin', 'Ntot', 'logn', 'logT', 'logf', 'rad']:
                if not hasattr(self.sys[int(s[1])], s[0]):
                    self.sys[int(s[1])].add(s[0])
            res = getattr(self.sys[int(s[1])], s[0]).set(val, attr)

        if s[0] in ['b', 'N']:
            while len(self.sys) <= int(s[1]):
                self.addSys()
            self.sys[int(s[1])].addSpecies(s[2])
            res = getattr(self.sys[int(s[1])].sp[s[2]], s[0]).set(val, attr)

        return res

    def update(self, what='all', ind='all', redraw=True):

        for i, sys in enumerate(self.sys):
            if ind == 'all' or i == ind:
                for k, s in sys.sp.items():
                    if what in ['all', 'b', 'turb', 'kin']:
                        if s.b.addinfo != '' and s.b.addinfo != 'consist':
                            s.b.val = sys.sp[s.b.addinfo].b.val
                        elif s.b.addinfo == 'consist':
                            s.b.val = doppler(k, sys.turb.val, sys.kin.val)
                    if what in ['all', 'me', 'dtoh']:
                        if s.N.addinfo == 'me' and 'HI' in sys.sp.keys():
                            if 'DI' not in k and hasattr(self, 'me'):
                                s.N.val = abundance(k, sys.sp['HI'].N.val, self.me.val)
                            elif 'DI' in k and hasattr(self, 'dtoh'):
                                s.N.val = sys.sp['HI'].N.val + self.dtoh.val

                if what in ['all', 'Ntot', 'logn', 'logT', 'logf', 'rad']:
                    if hasattr(sys, 'Ntot'):
                        sys.pyratio()

        if what in ['all', 'res']:
            if self.res_fit and self.res_num > 0:
                for i in range(self.res_num):
                    if i < len(self.parent.s):
                        self.parent.s[int(getattr(self, 'res_'+str(i)).addinfo[4:])].resolution = self.getValue('res_'+str(i))

        if what in ['all', 'cf']:
            if redraw and self.cf_fit:
                for i in range(self.cf_num):
                    try:
                        self.parent.plot.pcRegions[i].updateFromFit()
                    except:
                        pass

        for k, v in self.tieds.items():
            self.setValue(k, self.getValue(v))

    def getPar(self, name):
        s = name.split('_')
        par = None
        if s[0] in ['mu', 'me', 'dtoh']:
            if hasattr(self, s[0]):
                par = getattr(self, s[0])

        if s[0] in ['cont', 'res', 'cf', 'dispz', 'disps']:
            if hasattr(self, name):
                par = getattr(self, name)

        if s[0] in ['z', 'turb', 'kin', 'Ntot', 'logn', 'logT', 'logf', 'rad']:
            if len(self.sys) > int(s[1]) and hasattr(self.sys[int(s[1])], s[0]):
                par = getattr(self.sys[int(s[1])], s[0])

        if s[0] in ['b', 'N']:
            if len(self.sys) > int(s[1]) and s[2] in self.sys[int(s[1])].sp and hasattr(self.sys[int(s[1])].sp[s[2]], s[0]):
                par = getattr(self.sys[int(s[1])].sp[s[2]], s[0])

        if par is None:
            raise ValueError('Fit model has no {:} parameter'.format(name))
        else:
            return par

    def getValue(self, name, attr='val'):
        par = self.getPar(name)

        if par is None:
            raise ValueError('Fit model has no {:} parameter'.format(name))
        else:
            return getattr(par, attr)

    def list(self):
        return list(self.pars().values())

    def list_check(self):
        for par in self.list():
            par.check()

    def list_fit(self):
        return [par for par in self.list() if par.fit & par.vary]

    def list_vary(self):
        return [par for par in self.list() if par.vary]

    def pars(self):
        pars = OrderedDict()
        for attr in ['mu', 'me', 'dtoh', 'res']:
            if hasattr(self, attr):
                p = getattr(self, attr)
                pars[str(p)] = p
        if self.cont_fit and self.cont_num > 0:
            for i in range(self.cont_num):
                attr = 'cont_' + str(i)
                if hasattr(self, attr):
                    p = getattr(self, attr)
                    pars[str(p)] = p
        if self.res_fit and self.res_num > 0:
            for i in range(self.res_num):
                attr = 'res_' + str(i)
                if hasattr(self, attr):
                    p = getattr(self, attr)
                    pars[str(p)] = p
        if self.cf_fit and self.cf_num > 0:
            for i in range(self.cf_num):
                attr = 'cf_' + str(i)
                if hasattr(self, attr):
                    p = getattr(self, attr)
                    pars[str(p)] = p
        if self.disp_fit and self.disp_num > 0:
            for i in range(self.disp_num):
                for attr in ['dispz', 'disps']:
                    attr = attr + '_' + str(i)
                    if hasattr(self, attr):
                        p = getattr(self, attr)
                        pars[str(p)] = p
        if len(self.sys) > 0:
            for sys in self.sys:
                for attr in ['z', 'turb', 'kin', 'Ntot', 'logn', 'logT', 'logf', 'rad']:
                    if hasattr(sys, attr):
                        p = getattr(sys, attr)
                        pars[str(p)] = p
                for sp in sys.sp.values():
                    for attr in ['b', 'N']:
                        if hasattr(sp, attr):
                            p = getattr(sp, attr)
                            pars[str(p)] = p
        return pars

    def list_total(self):
        pars = OrderedDict()
        for sys in self.sys:
            for k, v in sys.total.items():
                pars['_'.join(['N', str(self.sys.index(sys)), k])] = v.N
        for k, v in self.total.sp.items():
            pars['_'.join(['N', 'total', k])] = v.N

        return pars

    def readPars(self, name):
        if name.count('*') > 0:
            name = name.replace('*' * name.count('*'), 'j' + str(name.count('*')))
        s = name.split()
        attrs = ['val', 'min', 'max', 'step', 'vary', 'addinfo']
        if len(s) == len(attrs):
            s.append('')

        if 'cont' in s[0]:
            self.cont_num = max(self.cont_num, int(s[0][5:]) + 1)
            self.cont_fit = True
        if 'res' in s[0]:
            self.res_fit = True
            self.res_num = max(self.res_num, int(s[0][4:]) + 1)
        if 'cf' in s[0]:
            self.cf_fit = True
            self.parent.plot.add_pcRegion()
        if 'disp' in s[0]:
            self.disp_fit = True
            self.disp_num = max(self.disp_num, int(s[0][6:]) + 1)

        for attr, val in zip(reversed(attrs), reversed(s[1:])):
            self.setValue(s[0], val, attr)
            if attr == 'val':
                self.setValue(s[0], float(s[4]), 'unc')

        if 'cf' in s[0]:
            self.parent.plot.pcRegions[-1].updateFromFit()

    def showLines(self, sp=None):
        if sp is None:
            sp = list(set([s for sys in self.sys for s in sys.sp.keys()]))
        for s in sp:
            self.parent.console.exec_command('show ' + s)
            #self.parent.console.exec_command('')

    def fromLMfit(self, result):
        for p in result.params.keys():
            par = result.params[p]
            name = str(par.name).replace('l4', '****').replace('l3', '***').replace('l2', '**').replace('l1', '*')
            self.setValue(name, self.pars()[name].ref(par.value), 'val')
            print(p, par.stderr)
            if isinstance(self.pars()[name].ref(par.stderr, attr='unc'), float):
                self.setValue(name, self.pars()[name].ref(par.stderr, attr='unc'), 'unc')
                self.setValue(name, self.pars()[name].ref(par.stderr, attr='unc'), 'step')
            else:
                self.setValue(name, 0, 'unc')

    def save(self):
        self.saved = [copy(l) for l in self.list()]

    def load(self):
        for p, saved in zip(self.pars(), self.saved):
            print(p, saved.val)
            self.setValue(p, saved.val)

    def setSpecific(self):
        self.addSys(z=2.8083543)
        self.setValue('b_0_SiIV', 10.6)
        self.setValue('N_0_SiIV', 12.71)
        self.addSys(z=2.8085)
        self.setValue('b_1_SiIV', 7.6)
        self.setValue('N_1_SiIV', 12.71)

    def __str__(self):
        return '\n'.join([str(s) for s in self.sys])


# Classes for parallelization
class spectra(list):
    def __init__(self):
        super(spectra).__init__()

    def set_lines(self):
        for s in self:
            s.set_lines()

class spec:
    def __init__(self, parent, x, y, err):
        self.x = x
        self.y = y
        self.err = err
        self.fit = None

    def set_lines(self, tlim=0.01, all=True, debug=False):
        """
        Function to prepare lines to fit.
          - ind         : specify component to fit
          - all         : if all then look for all the lines located in the  normalized spectrum

        Prepared lines where fit will be calculated are stored in self.fit_lines list.
        """
        self.fit_lines = []

        if self.x.shape[0] > 0:
            for sys in self.fit.sys:
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
                                cf = getattr(self.parent.fit, 'cf_' + str(i))
                                cf_sys = cf.addinfo.split('_')[0]
                                cf_exp = cf.addinfo.split('_')[1] if len(cf.addinfo.split('_')) > 1 else 'all'
                                if (cf_sys == 'all' or sys.ind == int(cf_sys[3:])) and (
                                                cf_exp == 'all' or self.ind() == int(cf_exp[3:])) and l.l() * (
                                            1 + l.z) > cf.min and l.l() * (1 + l.z) < cf.max:
                                    l.cf = i
                        if all:
                            if any([x[0] < p < x[-1] for p in l.range]):
                                self.fit_lines += [l]
                        else:
                            if np.sum(np.where(np.logical_and(x >= l.range[0], x <= l.range[1]))) > 0:
                                self.fit_lines += [l]
        if debug:
            print('findFitLines', self.fit_lines, [l.cf for l in self.fit_lines])

    def chi(self):
        pass

class calc_fit:
    def __init__(self, parent):
        self.parent = parent

    def set_data(self, data):
        self.s = spectra(self)
        for d in data:
            self.s.append(spec(self, d[0], d[1], d[2]))

    def set_model(self, pars, fit=None):
        if fit is None:
            self.fit = fitPars(self.parent)
            self.fit.readPars(pars)
        else:
            self.fit = fit

    def set_lines(self, lines):
        self.lines = lines


