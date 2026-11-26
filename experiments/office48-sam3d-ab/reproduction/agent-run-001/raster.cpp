#include <algorithm>
#include <cmath>
#include <vector>
#include <cstdint>

// Numeric silhouette proxy only. Final scores use the unchanged Blender renderer.
extern "C" void raster(const float* vertices, int nv, const int32_t* faces, int nf,
                       const double* transform, const double* rt, const double* k,
                       int width, int height, float* depth) {
    std::fill(depth, depth + width * height, 1e10f);
    std::vector<double> xx(nv), yy(nv), zz(nv);
    for (int i=0; i<nv; ++i) {
        const float* p=vertices+3*i;
        double world[3];
        for (int j=0;j<3;++j)
            world[j]=transform[4*j]*p[0]+transform[4*j+1]*p[1]+transform[4*j+2]*p[2]+transform[4*j+3];
        double camera[3];
        for (int j=0;j<3;++j)
            camera[j]=rt[4*j]*world[0]+rt[4*j+1]*world[1]+rt[4*j+2]*world[2]+rt[4*j+3];
        zz[i]=camera[2];
        if (camera[2]>.001) {
            xx[i]=(k[0]*camera[0]+k[1]*camera[1])/camera[2]+k[2];
            yy[i]=(k[3]*camera[0]+k[4]*camera[1])/camera[2]+k[5];
        }
    }
    for (int f=0;f<nf;++f) {
        int a=faces[3*f],b=faces[3*f+1],c=faces[3*f+2];
        if (zz[a]<=.001 || zz[b]<=.001 || zz[c]<=.001) continue;
        double ax=xx[a],ay=yy[a],bx=xx[b],by=yy[b],cx=xx[c],cy=yy[c];
        int xmin=std::max(0,(int)std::floor(std::min({ax,bx,cx})));
        int xmax=std::min(width-1,(int)std::ceil(std::max({ax,bx,cx})));
        int ymin=std::max(0,(int)std::floor(std::min({ay,by,cy})));
        int ymax=std::min(height-1,(int)std::ceil(std::max({ay,by,cy})));
        if (xmin>xmax || ymin>ymax) continue;
        double den=(by-cy)*(ax-cx)+(cx-bx)*(ay-cy);
        if (std::abs(den)<1e-10) continue;
        for (int y=ymin;y<=ymax;++y) for (int x=xmin;x<=xmax;++x) {
            double u=((by-cy)*(x+.5-cx)+(cx-bx)*(y+.5-cy))/den;
            double v=((cy-ay)*(x+.5-cx)+(ax-cx)*(y+.5-cy))/den;
            double w=1-u-v;
            if (u<0 || v<0 || w<0) continue;
            float z=1.0/(u/zz[a]+v/zz[b]+w/zz[c]);
            depth[y*width+x]=std::min(depth[y*width+x],z);
        }
    }
}
