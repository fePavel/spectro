import matplotlib.cm as cm
from matplotlib.colors import ListedColormap, LogNorm
import matplotlib.pyplot as plt
from matplotlib.transforms import Affine2D
import mpl_toolkits.axisartist.floating_axes as floating_axes
import numpy as np
from pyqtgraph.Qt import QtCore, QtGui
import pyqtgraph.opengl as gl
from scipy import interpolate, integrate, optimize
from scipy.stats import gaussian_kde, rv_continuous, norm

class distr1d():
    """
    Dealing with 1d distributions.

    Example of usage:
    d = distr1d(x, y), where x and y array specified distribution

    Make point estimate:
    d.dopoint()

    Make interval estimate:
    d.dointerval(conf=0.683)

    Make plot:
    d.plot(conf=0.683)
    """
    def __init__(self, x, y=None, xtol=1e-5, debug=False, name='par'):
        self.x = x
        if y is not None:
            self.y = y
        else:
            self.kde()
        self.xtol = xtol
        self.debug = debug
        self.name = name
        self.normalize()
        self.interpolate()

    def kde(self):
        kde = gaussian_kde(self.x)
        x = np.linspace(np.min(self.x), np.max(self.x), np.max([100, int(np.sqrt(len(self.x)))]))
        self.y = kde(x)
        self.x = x

    def normalize(self):
        inter = interpolate.interp1d(self.x, self.y)
        norm = integrate.quad(inter, self.x[0], self.x[-1])
        self.y = self.y / norm[0]
        self.ymax = np.max(self.y)

    def interpolate(self, kind='linear'):
        self.inter = interpolate.interp1d(self.x, self.y, kind=kind, bounds_error=False, fill_value=0)

    def minter(self, x):
        return -self.inter(x)

    def level(self, x, level):
        return self.inter(x) - level

    def plot(self, x=None, conf=None, kind='center', color='orangered', ax=None, xlabel=None, ylabel=None, fontsize=16, alpha=0.3):
        if ax is None:
            fig, ax = plt.subplots()
        if x is None:
            x = self.x
        ax.plot(x, self.inter(x), '-', color=color, lw=1.5)
        if conf is not None:
            self.dointerval(conf=conf, kind=kind)
            print('interval plot', self.interval)
            mask = np.logical_and(x >= self.interval[0], x <= self.interval[1])
            ax.fill_between(x[mask], self.inter(x)[mask], facecolor=color, alpha=alpha, interpolate=True)

        ax.tick_params(axis='both', which='major', labelsize=fontsize - 2)
        if xlabel is not None:
            ax.set_xlabel(xlabel, fontsize=fontsize)

        if ylabel is None:
            ax.set_ylabel('pdf', fontsize=fontsize)
        else:
            ax.set_ylabel(ylabel, fontsize=fontsize)

        return ax

    def minmax(self, level):
        ind = np.argmax(self.y)
        if level > 0 and level < self.ymax:
            if 1:
                try:
                    self.xmin = optimize.bisect(self.level, self.x[0], self.x[ind], args=(level))
                except ValueError:
                    self.xmin = self.x[0]
                try:
                    self.xmax = optimize.bisect(self.level, self.x[ind], self.x[-1], args=(level))
                except ValueError:
                    self.xmax = self.x[-1]
            else:
                step = (self.x[ind + 1] - self.x[ind - 1]) / 10
                o = {'xtol': self.xtol, 'epsfcn': step}
                self.xmin = optimize.root(self.level, self.x[ind-3], args=(level), method='lm', disp=self.debug, options=o).x
                self.xmax = optimize.root(self.level, self.x[ind+3], args=(level), method='lm', disp=self.debug, options=o).x
        elif level > self.ymax:
            self.xmin, self.xmax = self.point, self.point
        elif level <= 0:
            self.xmin, self.xmax = self.x[0], self.x[-1]

        return self.xmin, self.xmax

    def func_twoside(self, level, conf):
        xmin, xmax = self.minmax(level)
        return integrate.quad(self.inter, xmin, xmax)[0] - conf

    def func_oneside(self, x, conf, kind='left'):
        if kind == 'right':
            return integrate.quad(self.inter, x, self.x[-1])[0] - conf
        elif kind == 'left':
            return integrate.quad(self.inter, self.x[0], x)[0] - conf

    def dopoint(self, verbose=True):
        """
        Point estimate of distribution
        :return:
            - point estimate?
        """
        self.point = optimize.fmin(self.minter, self.x[np.argmax(self.y)], xtol=self.xtol, disp=self.debug)[0]
        self.ymax = self.inter(self.point)
        if self.debug or verbose:
            print('point:', self.point, self.x[np.argmax(self.y)])
        return self.point

    def dointerval(self, conf=0.683, kind='center', verbose=False):
        """
        Interval estimate for given confidence level
        parameters:
            - conf        :  confidence level
            - kind        :  type of the interval, can be: 'center' (default), 'left', 'right'
            - verbose     :  verbose output
        return: interval, level
            - interval    :  estimated interval
            - level       :  level of pdf
        """
        nd = norm()
        self.dopoint(verbose=False)
        if kind == 'center':
            n = self.ymax / (nd.pdf(0) / (nd.pdf(nd.interval(conf)[0]) / 2))
            res = optimize.fsolve(self.func_twoside, n, args=(conf), xtol=self.xtol, full_output=self.debug)
            self.interval = self.minmax(res[0])
        else:
            res = optimize.fsolve(self.func_oneside, self.point, args=(conf, kind), xtol=self.xtol, full_output=self.debug)
            if kind == 'right':
                self.interval = [res[0], self.x[-1]]
            elif kind == 'left':
                self.interval = [self.x[0], res[0]]

        if self.debug or verbose:
            print('interval:', self.interval[0], self.interval[1])
        return self.interval, res[0]


    def stats(self, conf=0.683, kind='center', latex=0, name=None):
        if name is not None:
            self.name = name
        self.dopoint(verbose=(latex<0))
        self.dointerval(conf=conf, kind=kind, verbose=(latex<0))
        if latex >= 0:
            print("{name} = {0:.{n}f}^{{+{1:.{n}f}}}_{{-{2:.{n}f}}}".format(self.point, self.interval[1] - self.point, self.point - self.interval[0], n=latex, name=self.name))

    def pdf(self, x):
        return self.inter(x)

    def rvs(self, n=1):
        class gen(rv_continuous):
            def __init__(self, parent, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.parent = parent

            def _pdf(self, x):
                return self.parent.pdf(x)

        return gen(self, a=self.x[0], b=self.x[-1]).rvs(size=n)

    def latex(self, f=2):
        return "{0:.{n}f}^{{+{1:.{n}f}}}_{{-{2:.{n}f}}}".format(self.point, self.interval[1] - self.point, self.point - self.interval[0], n=f)

class distr2d():
    def __init__(self, x, y, z=None, xtol=1e-5, debug=False):
        if z is None:
            self.x = np.linspace(np.min(x), np.max(x), int(np.sqrt(len(x))))
            self.y = np.linspace(np.min(y), np.max(y), int(np.sqrt(len(y))))
            X, Y = np.meshgrid(self.x, self.y)
            z = gaussian_kde([x, y])
            self.z = z(np.vstack([X.flatten(), Y.flatten()])).reshape(X.shape)

        elif len(z.shape) == 1 and len(x.shape) == 1 and len(y.shape) == 1:
            self.x = np.unique(sorted(x))
            self.y = np.unique(sorted(y))
            self.z = np.zeros([len(self.y), len(self.x)])
            for i, xi in enumerate(self.x):
                for k, yk in enumerate(self.y):
                    ind = np.where((xi == x) * (yk == y))[0]
                    if len(ind) > 0:
                        self.z[k, i] = z[ind[0]]
        elif len(x) in z.shape and len(y) in z.shape:
            self.x = x
            self.y = y
            self.z = z

        self.X, self.Y = np.meshgrid(self.x, self.y)
        self.zmax = None
        self.xtol = xtol
        self.debug = debug
        self.normalize()
        self.interpolate()
        #self.plot()

    def normalize(self):
        if 1:
            norm = np.abs(integrate.simps(integrate.simps(self.z, self.y, axis=0), self.x))
        else:
            # not working ???!!!
            inter = interpolate.interp2d(self.x, self.y, self.z, kind='linear', fill_value=0)
            norm = integrate.dblquad(inter, self.x[0], self.x[-1], lambda x: self.y[0], lambda x: self.y[-1])
        if self.debug:
            print('norm:', norm)
        self.z = self.z / norm

    def interpolate(self):
        if 1:
            self.inter = interpolate.interp2d(self.x, self.y, self.z, kind='cubic', fill_value=0)
            #self.inter = interpolate.Rbf(self.x, self.y, self.z, function='multiquadric', smooth=0.1)
        else:
            self.inter = interpolate.RectBivariateSpline(self.x, self.y, self.z, kx=3, ky=3)
        #xi, yi = 5, 14
        #print(self.inter(self.x[xi], self.y[yi]), self.z[yi, xi], self.x[xi], self.y[yi])
        #print(self.inter(self.x[xi+1], self.y[yi+1]), self.z[yi+1, xi+1], self.x[xi+1], self.y[yi+1])
        #print(self.inter((self.x[xi]+self.x[xi+1])/2, (self.y[yi]+self.y[yi+1])/2))

    def minter(self, x):
        return -self.inter(x[0], x[1])[0]

    def level(self, x, level):
        return self.inter(x) - level

    def minmax(self, level):
        if level > 0 and level < self.zmax:
            x = self.X[self.z > level].flatten()
            self.xmin, self.xmax = np.min(x), np.max(x)
            y = self.Y[self.z > level].flatten()
            self.ymin, self.ymax = np.min(y), np.max(y)
        elif level > self.zmax:
            self.xmin, self.xmax = self.point[0], self.point[0]
            self.ymin, self.ymax = self.point[1], self.point[1]
        elif level < 0:
            self.xmin, self.xmax = self.x[0], self.x[-1]
            self.ymin, self.ymax = self.y[0], self.y[-1]
        return [self.xmin, self.xmax], [self.ymin, self.ymax]

    def func(self, level, conf, x=None, y=None, z=None):
        if x is None:
            x = self.x
        if y is None:
            y = self.y
        if z is None:
            z = self.z
        zs = np.copy(z)
        zs[zs < level] = 0
        return integrate.simps(integrate.simps(zs, y, axis=0), x) - conf

    def dopoint(self, verbose=False):
        """
        Point estimate of distribution

        return: point, level
            - point         :  point estimate
        """
        ind = np.argwhere(self.z == np.nanmax(self.z.flatten()))
        self.point = optimize.fmin(self.minter, [self.x[ind[0][1]], self.y[ind[0][0]]], xtol=self.xtol, disp=self.debug)
        self.zmax = self.inter(self.point[0], self.point[1])
        if self.debug or verbose:
            print('point estimate:', self.point[0], self.point[1], self.zmax)
        return self.point

    def level(self, conf=0.683):
        """
        Level of pdf at given confidence level
        parameters:
            - conf           :  confidence level

        return: level
            - level          :  pdf value above pdf contains conf level of probability
        """
        x, y = np.linspace(np.min(self.x), np.max(self.x), 300), np.linspace(np.min(self.y), np.max(self.y), 300)
        z = self.inter(x, y)
        if 1:
            res = optimize.bisect(self.func, 0, self.zmax, args=(conf, x, y, z), xtol=self.xtol, disp=self.debug)
        else:
            res = optimize.fsolve(self.func, self.zmax/2, args=(conf, x, y, z), xtol=self.xtol, disp=self.debug)[0]
        if self.debug:
            print('fsolve:', res)

        return res

    def dointerval(self, conf=0.683, verbose=False):
        """
        Estimate the interval for the both parameters.
        parameters:
            - conf            :  confidence levels

        return: x_interval, y_interval, level
            - x_interval      :  interval values for x
            - y_interval      :  interval values for y
            - level           :  level of pdf corresponding to area equal confidence.
        """
        nd = norm()
        self.dopoint()
        n = self.zmax / (nd.pdf(0) / (nd.pdf(nd.interval(conf)[0]) / 2))
        res = optimize.fsolve(self.func, n, args=(conf), xtol=self.xtol, full_output=self.debug)
        self.interval = self.minmax(res[0])

        level = self.level(conf=conf)
        self.interval = self.minmax(level)
        if self.debug or verbose:
            print('interval:', self.interval[0], self.interval[1])
        return self.interval[0], self.interval[1], res[0]

    def plot_3d(self, conf_levels=None):
        app = QtGui.QApplication([])
        w = gl.GLViewWidget()
        w.show()
        w.setWindowTitle('2d distribution plot')
        w.setCameraPosition(distance=50)
        g = gl.GLGridItem()
        g.scale(1, 1, 1)
        g.setDepthValue(10)  # draw grid after surfaces since they may be translucent
        w.addItem(g)
        if 1:
            x, y = np.linspace(self.x[0], self.x[-1], 300), np.linspace(self.y[0], self.y[-1], 300)
            p1 = gl.GLSurfacePlotItem(x=x, y=y, z=self.inter(x, y), shader='normalColor')
        else:
            p1 = gl.GLSurfacePlotItem(x=self.x, y=self.y, z=self.z, shader='normalColor')
        x_s, y_s = 20 / (self.x[-1] - self.x[0]), 20 / (self.y[-1] - self.y[0])
        x_t, y_t = -(self.x[-1]+self.x[0]) / 2 * x_s, -(self.y[-1]+self.y[0]) / 2 * y_s
        p1.scale(x_s, y_s, 10 / np.max(self.z.flatten()))
        p1.translate(x_t, y_t, 0)
        w.addItem(p1)
        if conf_levels is not None:
            fig, ax = plt.subplots()
            if isinstance(conf_levels, float):
                conf_levels = [conf_levels]
            for c in conf_levels:
                print(c)
                cs = ax.contour(self.X, self.Y, self.z, levels=[c], origin='lower')
                p = cs.collections[0].get_paths()
                for l in p:
                    x, y = l.vertices.transpose()[0], l.vertices.transpose()[1]
                    z = np.ones_like(x) * c
                    line = gl.GLLinePlotItem(pos=np.vstack([y, x, z]).transpose(), antialias=True)
                    line.scale(y_s, x_s, 10 / np.max(self.z.flatten()))
                    line.translate(y_t, x_t, 0)
                    w.addItem(line)
        app.instance().exec_()

    def plot_contour(self, conf_levels=None, ax=None, xlabel='', ylabel='', limits=None, ls=['--'],
                     color='dodgerblue', color_point='gold', cmap='PuBu', alpha=1.0, colorbar=False,
                     font=14, title=None, zorder=1, label=None):
        if ax == None:
            fig, ax = plt.subplots()
        self.dopoint()
        if conf_levels == None:
            conf_levels = [0.683]
        if type(conf_levels) in [float, int]:
            conf_levels = [conf_levels]
        conf_levels = np.sort(conf_levels)[::-1]
        if cmap is not None:
            if isinstance(cmap, str):
                cmap = getattr(cm, cmap)
            my_cmap = cmap(np.arange(cmap.N))
            my_cmap[:,-1] = np.linspace(alpha*(0.6+0.4*alpha), 0.6+0.4*alpha, cmap.N)
            my_cmap = ListedColormap(my_cmap)
            cs = ax.contourf(self.X, self.Y, self.z / self.zmax, 100, cmap=my_cmap, zorder=zorder)
        if color is not None:
            levels = [self.level(c) for c in conf_levels]
            if limits == None or limits == 0:
                c = ax.contour(self.X, self.Y, self.z / self.zmax, levels=levels / self.zmax, colors=color, lw=0.5, linestyles='-',
                               zorder=zorder, label=label)
            else:
                c = ax.contour(self.X, self.Y, self.z / self.zmax, levels=levels / self.zmax, colors=color, lw=0.5, linestyles='-', alpha=0)
                x, y = c.collections[0].get_segments()[0][:,0], c.collections[0].get_segments()[0][:,1]
                inter = interpolate.interp1d(x, y)
                x = np.linspace(x[0], x[-1], 30)
                ax.plot(x, inter(x), '-', c=color)
                if limits < 0:
                    lolims, uplims = False, True
                if limits > 0:
                    lolims, uplims = True, False
                x = np.linspace(x[0], x[-1], 10)
                ax.errorbar(x, inter(x), yerr=np.abs(limits), lolims=lolims, fmt='o', color=color, uplims=uplims, markersize=0, capsize=0, zorder=zorder, label=label)
        if ls is not None:
            for c, s in zip(c.collections[:len(ls)], ls[::-1]):
                c.set_dashes(s)
        if color_point is not None:
            ax.scatter(self.point[0], self.point[1], s=200, color=color_point, edgecolors='k', marker='*', zorder=50)
        if colorbar:
            fig.colorbar(cs, ax=ax) #, shrink=0.9)
        ax.set_xlabel(xlabel, fontsize=font)
        ax.set_ylabel(ylabel, fontsize=font)
        ax.tick_params(axis='both', which='major', labelsize=font)
        if title is not None:
            ax.set_title(title, fontdict={'fontsize': font})
        return ax

    def plot(self, fig=None, frac=0.1, indent=0.15, color_marg='dodgerblue',
             conf_levels=None, xlabel='', ylabel='', limits=None, ls=None,
             color='greenyellow', color_point='gold', cmap='PuBu', alpha=1.0, colorbar=False,
             font=14, title=None, zorder=1):
        if fig is None:
            fig = plt.figure()
        ax = fig.add_axes([indent, indent, 1 - indent - frac, 1 - indent - frac])
        ax.set_position([indent, indent, 1 - indent - frac, 1 - indent - frac])
        self.plot_contour(ax=ax, conf_levels=conf_levels, xlabel=xlabel, ylabel=ylabel, limits=limits, ls=ls,
                     color=color, color_point=color_point, cmap=cmap, alpha=alpha, colorbar=colorbar,
                     font=font, title=title, zorder=zorder)

        x, y = ax.get_xlim(), ax.get_ylim()
        #helper = floating_axes.GridHelperCurveLinear(Affine2D().rotate_deg(-90), extremes=(0, 4, 0, 4))
        #ax = floating_axes.FloatingSubplot(fig, [1 - frac, indent, frac, 1 - indent - frac], grid_helper=helper)

        dy = self.marginalize('x')
        ax = fig.add_axes([1 - frac, indent, frac, 1 - indent - frac])
        #ax.set_position([1 - frac, indent, frac, 1 - indent - frac])
        ax.set_axis_off()
        ax.plot(dy.inter(dy.x), dy.x, '-', color=color_marg, lw=1.5)
        ax.set_ylim(y)
        ax.set_xlim([0 + ax.get_xlim()[1]/50, ax.get_xlim()[1]])

        dx = self.marginalize('y')
        ax = fig.add_axes([indent, 1 - frac, 1 - indent - frac, frac])
        #ax.set_position([indent, 1 - frac, 1 - indent - frac, frac])
        ax.set_axis_off()
        ax.plot(dx.x, dx.inter(dx.x), '-', color=color_marg, lw=1.5)
        ax.set_xlim(x)
        ax.set_ylim([0 + ax.get_ylim()[1]/50, ax.get_ylim()[1]])

        fig.tight_layout()
        return fig

    def marginalize(self, over='y'):
        """
        marginaize to 1d distribution over specified axis
        parameters:
            - over              :  axis over which perform marginalization, 'x' or 'y'
        return: distr
            - distr             :  1d distribution object
        """
        if over == 'y':
            return distr1d(self.x, integrate.simps(self.z, self.y, axis=0), debug=self.debug)
        else:
            return distr1d(self.y, integrate.simps(self.z, self.x, axis=1), debug=self.debug)

    def pdf(self, x, y):
        """
        return pdf of the distribution
        parameters:
            - x          :  x
            - y          :  y
        """
        return self.inter(x, y)

    def rvs(self, n=1, xrange=None, yrange=None):
        """
        Generate the random sample from the distribution using rejection sampling
        parameters:
            - n            : sample size to generate
            - xrange       : range of x to sample
            - yrange       : range of y to sample
        return: sample,
            - sample       : sample
        """
        if self.zmax is None:
            self.dopoint()
        print(self.zmax)

        if xrange is None:
            xrange = (self.x[0], self.x[-1])

        if yrange is None:
            yrange = (self.y[0], self.y[-1])

        x, y = [-2, -1], [-1.5, -0.5]
        num = n
        genx, geny = [], []
        while len(genx) < n:
            x = np.random.uniform(xrange[0], xrange[1], num)
            y = np.random.uniform(yrange[0], yrange[1], num)
            w = np.random.uniform(size=num)
            t = Timer()
            pdf = np.array([self.pdf(xx, yy)[0] for xx, yy in zip(x, y)])
            #pdf = np.diag(self.pdf(x, y))
            mask = (pdf / self.zmax) > w
            #if mask.sum() > 0:
            #    print(pdf[mask] / self.zmax, w[mask], x[mask], y[mask])
            #print(genx, geny)
            genx += list(x[mask])
            geny += list(y[mask])
        m = np.random.choice(len(genx), n)
        return np.asarray(genx)[m], np.asarray(geny)[m]


def powerlaw(a, b, g, size=1):
    """Power-law gen for pdf(x)\propto x^{g-1} for a<=x<=b"""

    r = np.random.random(size=size)
    ag, bg = a ** g, b ** g
    return (ag + (bg - ag) * r) ** (1. / g)


if __name__ == '__main__':

    if 1:
        x = np.linspace(1, 10, 40)
        y = np.linspace(0, 3, 40)
        x, y = np.meshgrid(x, y)
        x, y = x.flatten(), y.flatten()
        x, y = np.delete(x, x[0]), np.delete(y, y[0])
        z = np.exp(- (x - 5)**2 - (y - 1)**2)
        d = distr2d(x, y, z)
        d.plot(frac=0.15)
        d1 = d.marginalize('x')
        d1.stats(latex=3)
        plt.show()