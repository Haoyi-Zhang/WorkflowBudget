"""Direct vector illustrations of the declared finite workflow semantics."""
import argparse
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch

plt.rcParams.update({'font.family':'STIXGeneral','mathtext.fontset':'stix',
    'font.size':9.5,'pdf.fonttype':42,'text.usetex':False,'axes.unicode_minus':False})

class Drawing:
    def __init__(self,w,h):
        self.fig=plt.figure(figsize=(w/2.54,h/2.54))
        self.ax=self.fig.add_axes([0,0,1,1],xlim=(0,w),ylim=(0,h))
        self.ax.set_aspect('equal');self.ax.axis('off');self.labels=[]
    def text(self,x,y,s,size=9.5):
        self.labels.append(self.ax.text(x,y,s,ha='center',va='center',fontsize=size))
    def arrow(self,a,b):
        self.ax.add_patch(FancyArrowPatch(a,b,arrowstyle='-|>',mutation_scale=9,
                          linewidth=.7,color='black'))
    def save(self,out,name):
        self.fig.canvas.draw();r=self.fig.canvas.get_renderer();e=self.fig.bbox
        for t in self.labels:
            b=t.get_window_extent(r)
            if b.x0<e.x0 or b.x1>e.x1 or b.y0<e.y0 or b.y1>e.y1:
                raise ValueError('Clipped label: '+t.get_text())
        self.fig.savefig(out/(name+'.pdf'),metadata={'Creator':'Python Matplotlib',
                         'Producer':None,'CreationDate':None,'ModDate':None})
        plt.close(self.fig)

def projection(out):
    d=Drawing(14.5,5.8)
    for x,y,s in [(3.5,4.6,r'$(p,q,A,B,\nu)$'),
                  (11.0,4.6,r"$(p',q',A',B',\nu')$"),
                  (3.5,1.2,r'$(p,q,A,B,\mu)$'),
                  (11.0,1.2,r"$(p',q',A',B',\mu')$")]:
        d.text(x,y,s)
    for y,ly in [(4.6,5.25),(1.2,.55)]:
        d.arrow((5.15,y),(8.95,y));d.text(7.05,ly,'Shared-key step',9)
    for x in (3.5,11.0):d.arrow((x,4.1),(x,1.7))
    d.text(1.65,2.9,r'$|_{\mathcal{L}(p,q)}$')
    d.text(12.9,2.9,r"$|_{\mathcal{L}(p',q')}$")
    d.save(out,'projection')

def budget(out):
    d=Drawing(14.5,5.3)
    d.text(1.5,3.7,'Split')
    d.text(.65,2.2,'Fail');d.text(2.4,2.2,r'Return $(r)$')
    d.arrow((1.3,3.3),(.75,2.6));d.arrow((1.7,3.3),(2.25,2.6))
    xs=[6.0,8.25,10.5,12.75]
    d.text(4.55,4.45,r'Budget $b$')
    for b,x in enumerate(xs):d.text(x,4.45,str(b))
    for y,name,outputs in [(3.4,'FIFO',[0,0,0,1]),(1.55,'LIFO',[0,0,1,1])]:
        d.text(4.55,y,name)
        for i,x in enumerate(xs):
            d.ax.plot([x],[y],'o',color='black',markersize=2.3)
            if i<3:d.arrow((x+.06,y),(xs[i+1]-.06,y))
            d.text(x,y-.58,r'$\{r\}$' if outputs[i] else r'$\varnothing$')
    d.save(out,'budget-example')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--outdir',type=Path,
        default=Path(__file__).resolve().parent)
    out=parser.parse_args().outdir;out.mkdir(parents=True,exist_ok=True)
    for draw in (projection,budget):draw(out)
