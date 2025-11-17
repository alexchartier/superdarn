/* metereoproc.c
   =============
   Author: Kevin O'Rourke, adapted by R.J.Barnes
*/

#include <stdio.h>
#include <stdlib.h>
#include <ctype.h>
#include <errno.h>
#include <time.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <string.h>
#include <unistd.h>
#include <math.h>
#include <zlib.h>
#include "rtypes.h"
#include "option.h"
#include "rtime.h"
#include "rmath.h"
#include "radar.h" 

#include "cfitdata.h"
#include "cfitread.h"
#include "rpos.h"

#include "errstr.h"
#include "hlpstr.h"

#include "meteor.h"
#include "math.h"

#include "nrutil.h"

struct RadarNetwork *network;
struct Radar *radar;
struct RadarSite *site;

struct CFitdata *cfit;
struct OptionData opt;

int cnt=0;

struct metdata {
  int yr,mo,dy,hr,mt,sc;
  int bmnum;
  int frang,rsep,rxrise;
  int max_gate;
  unsigned char flg[75];
  double vlos[75];
};

int num[24];
struct metdata *met[24];


double bm_total[32];
double bm_sdtmp[32];
int bm_count[32];
int num_avgs=0;

int beams=0;
double vlos[32];
double sdev[32];

double vx,vy;
double vm;
double sdvx,sdvy;
double lat,lon,rho,vmlat,vmlon;

double *a;
double **u;
double **v;
double *w;
double *x;
double *y;
double *sig;

double coseps;
double chisq;

double **cvm;

double calc_coseps(double range) {
  double eps;
  eps = asin(METEOR_HEIGHT/range);
  return cos(eps);
};


double calc_azi(int bmnum) {
  double azi;
  azi = site->bmsep*(bmnum-7.5)+site->boresite;
  return (azi*PI/180.0);
};

void cosfunc(double x, double afunc[], int ma) {
	afunc[1] = -cos(x);
	afunc[2] = sin(x);
};


int main (int argc,char *argv[]) {
  int arg;
  unsigned char vb=0;
  unsigned char help=0;

  int i,j;
  struct CFitfp *cfp=NULL;
  FILE *fp;
  int c;
  char *mz_str=NULL; 
  double max_vel = MAX_VEL;
  double min_sn = MIN_SN;
  double max_v_err = MAX_V_ERR;
  double max_w_l = MAX_W_L;
  int max_range = MAX_MET_RANGE;
  int vm_beam = -1;
  int min_beams = MIN_BEAMS;
  int bm_type = BM_TYPE;
  int max_gate=0;
  int st_id=-1;
  int req_hr=-1;
  int yr,mo,dy,hr,mt;
  double sc;
  int year,month,day;
  
  int frang,rsep,rxrise=0;
  int mxbm=16;  

  int bc=0;

  char *envstr;

  cfit=CFitMake();

  envstr=getenv("SD_RADAR");
  if (envstr==NULL) {
    fprintf(stderr,"Environment variable 'SD_RADAR' must be defined.\n");
    exit(-1);
  }

  fp=fopen(envstr,"r");

  if (fp==NULL) {
    fprintf(stderr,"Could not locate radar information file.\n");
    exit(-1);
  }

  network=RadarLoad(fp);
  fclose(fp); 
  if (network==NULL) {
    fprintf(stderr,"Failed to read radar information.\n");
    exit(-1);
  }

  envstr=getenv("SD_HDWPATH");
  if (envstr==NULL) {
    fprintf(stderr,"Environment variable 'SD_HDWPATH' must be defined.\n");
    exit(-1);
  }

  RadarLoadHardware(envstr,network);

  OptionAdd(&opt,"-help",'x',&help);
  OptionAdd(&opt,"vb",'x',&vb);
  OptionAdd(&opt,"mv",'d',&max_vel);
  OptionAdd(&opt,"ms",'d',&min_sn);
  OptionAdd(&opt,"me",'d',&max_v_err);
  OptionAdd(&opt,"mw",'d',&max_w_l);

  OptionAdd(&opt,"bm",'i',&vm_beam);

  OptionAdd(&opt,"mr",'i',&max_range);

  OptionAdd(&opt,"mb",'i',&min_beams);
  OptionAdd(&opt,"bm",'i',&vm_beam);

  OptionAdd(&opt,"mz",'t',&mz_str);

  OptionAdd(&opt,"hr",'i',&req_hr);

  arg=OptionProcess(1,argc,argv,&opt,NULL);   

  if (help==1) {
    OptionPrintInfo(stdout,hlpstr);
    exit(0);
  }

  if (mz_str !=NULL) {
     if (tolower(mz_str[0])=='m') bm_type=0;
     else bm_type=1;
  }
  
  if (arg==argc) {
    OptionPrintInfo(stdout,errstr);
    exit(-1);
  }
    
  for (c=arg;c<argc;c++) {

    cfp=CFitOpen(argv[c],0); 
    fprintf(stderr,"Opening file %s\n",argv[c]);
    if (cfp==NULL) {
      fprintf(stderr,"file %s not found\n",argv[c]);
      continue;
    }
 
    while (CFitRead(cfp,cfit) !=-1) {
      TimeEpochToYMDHMS(cfit->time,&yr,&mo,&dy,&hr,&mt,&sc);
      if (site==NULL) {
        radar=RadarGetRadar(network,cfit->stid);
        site=RadarYMDHMSGetSite(radar,yr,mo,dy,hr,mt,
                                    (int) sc);
        mxbm=site->maxbeam;
        st_id=cfit->stid;
        frang=cfit->frang;
        rsep=cfit->rsep;
        rxrise=cfit->rxrise;
        if (rxrise==0) rxrise=site->recrise;
        rxrise=site->recrise;
        if (vm_beam==-1) {
          float bstp;
	  if (site->geolat>0) {
	    bstp=site->boresite/site->bmsep;
	    vm_beam=round(site->maxbeam/2.0-0.5-bstp);
	  } else {
	    bstp=(180.0-site->boresite)/site->bmsep;
	    vm_beam=round(site->maxbeam/2.0-0.5+bstp);
	  }
          if (vm_beam<0) vm_beam=0;
          if (vm_beam>=site->maxbeam) vm_beam=site->maxbeam-1;
 	}
      }
      /* select the data */
        
      cnt=num[hr];
      if ((req_hr !=-1) && (hr !=req_hr)) continue;
      if (cfit->scan <0) continue;
      if (cfit->frang==0) continue;
      if (cfit->rsep==0) continue;
      if (met[hr]==NULL) met[hr]=malloc(sizeof(struct metdata));
      else met[hr]=realloc(met[hr],sizeof(struct metdata)*(cnt+1));
      memset(&met[hr][cnt],0,sizeof(struct metdata));
     
      
      met[hr][cnt].yr=yr;
      met[hr][cnt].mo=mo;
      met[hr][cnt].dy=dy;
      met[hr][cnt].hr=hr;
      met[hr][cnt].mt=mt;
      met[hr][cnt].sc=sc;
      met[hr][cnt].bmnum=cfit->bmnum;
      met[hr][cnt].frang=cfit->frang;
      met[hr][cnt].rsep=cfit->rsep;
      met[hr][cnt].rxrise=rxrise;
     
      max_gate=(max_range-cfit->frang)/cfit->rsep;
      met[hr][cnt].max_gate=max_gate;
      for (j=0;j<cfit->num;j++) {
        if (cfit->rng[j]>=max_gate) continue;
        i=cfit->rng[j];
        met[hr][cnt].flg[i]=0;
        if (fabs(cfit->data[j].v) > max_vel) continue;
        if (cfit->data[j].p_l < min_sn) continue;
        if (cfit->data[j].v_e >= max_v_err) continue;
        if (cfit->data[j].w_l > max_w_l) continue;
        met[hr][cnt].flg[i]=1;
        met[hr][cnt].vlos[i]=cfit->data[j].v;
      }
      num[hr]++;
    } 
    CFitClose(cfp);
  }



  x = dvector(1,mxbm);
  y = dvector(1,mxbm);
  sig = dvector(1,mxbm);
  a = dvector(1,2);
  u = dmatrix(1,mxbm,1,2);
  v = dmatrix(1,2,1,2);
  w = dvector(1,2);

  coseps = calc_coseps(max_range/2.0);

  cvm=dmatrix(1,2,1,2);

  fprintf(stdout,"# Vlos(max)=%.2f\n# S/N(min)=%.2f\n# range(max)=%d\n", 
                      max_vel, min_sn, max_range);
  fprintf(stdout, "# Verr(max)=%.2f\n# num_beams(min)=%d\n", max_v_err, 
                   min_beams);
  fprintf(stdout, "# w_l(max)=%.2f\n", max_w_l);
  if (bm_type == 0) fprintf(stdout,
    "# beam_num=%d\n# wind=meridional\n",vm_beam);
  else fprintf(stdout, 
    "# beam_num=%d\n# wind=zonal\n",vm_beam);
  fprintf(stdout, "# stid=%d\n", st_id);
 
  if (bm_type == 0) fprintf(stdout,
     "# year month day hour num_avgs frang rsep Vx Vy lat long Vm Vm_lat Vm_long sdev_Vx sdev_Vy\n");
  else fprintf(stdout, 
     "# year month day hour num_avgs frang rsep Vx Vy lat long Vz Vz_lat Vz_long sdev_Vx sdev_Vy\n");

  /* now do the fitting */

  hr=0;
  if (req_hr !=-1) hr=req_hr;
  do {
    cnt=num[hr];
    if (cnt==0) {
      fprintf(stderr,"No data.\n");
      if (req_hr !=-1) break;
      hr++;
      continue;
    }

    year=met[hr][0].yr;
    month=met[hr][0].mo;
    day=met[hr][0].dy;

    for (i=0;i<mxbm;i++) {
      bm_total[i]=0;
      bm_count[i]=0;
      bm_sdtmp[i]=0;
    }
    num_avgs=0; 
    beams=0;
    for (i=0;i<cnt;i++) {
      for (j=0;j<met[hr][i].max_gate;j++) {
        if (met[hr][i].flg[j]==0) continue;
        bm_total[met[hr][i].bmnum]+= met[hr][i].vlos[j];
        bm_count[met[hr][i].bmnum]++;
        num_avgs++;
      }
    }
 
    for (i=0;i<mxbm;i++) {
      if (bm_count[i] > 0) {
        beams++;
        vlos[i] =bm_total[i]/bm_count[i];
       } else vlos[i]=0;
    };


    for (i=0;i<cnt;i++) {
      for (j=0;j<met[hr][i].max_gate;j++) {
        if (met[hr][i].flg[j]==0) continue;
        bm_sdtmp[met[hr][i].bmnum]+=(met[hr][i].vlos[j]-
                                     vlos[met[hr][i].bmnum])*
	         (met[hr][i].vlos[j]-vlos[met[hr][i].bmnum]);
      
      }
    }
    for (i=0;i<mxbm;i++) {
      if (bm_count[i] > 1) {
        sdev[i] =sqrt(bm_sdtmp[i]/(bm_count[i]-1));
       } else {
        sdev[i]=1;
        vlos[i]=0;
      }
    }
      

    if (beams<min_beams) {
      fprintf(stderr,
              "Not enough beams of data to generate a velocity vector\n");
      if (req_hr !=-1) break;
      hr++;
      continue;
    }

  
    bc=0;
    for (i=0;i<mxbm;i++) {
      if (bm_count[i]>1) {
        x[++bc]=calc_azi(i);   
        y[bc] =vlos[i]/coseps; /* mean velocity */
        sig[bc] = sdev[i];	
      }
    }


 
    fprintf(stderr,"Fitting %d of %d beams\n",bc,mxbm);
 

    dsvdfit(x, y, sig, bc, a, 2, u, v, w, &chisq, &cosfunc);

  
    vx=a[1];
    vy=a[2];
  
    dsvdvar(v, 2, w, cvm);

    sdvx = sqrt(cvm[1][1]);
    sdvy = sqrt(cvm[2][2]);
  
    vm=vlos[vm_beam]/coseps;

    frang=met[hr][0].frang;
    rsep=met[hr][0].rsep;
    rxrise=met[hr][0].rxrise;  
    RPosGeo(0,7,3,site,frang,rsep,rxrise,METEOR_HEIGHT,&rho,
             &lat,&lon);

    RPosGeo(0,vm_beam,3,site,frang,rsep,rxrise,METEOR_HEIGHT,&rho,
             &vmlat,&vmlon);


    fprintf(stdout, "%4d %02d %02d %02d %d %d %d %.0f %.0f %.1f %.1f %.0f %.1f %.1f %.2f %.2f\n",
	  year,month,day,hr,num_avgs,frang,rsep,vx,vy,lat,lon,vm,vmlat,vmlon,sdvx,sdvy);

    if (req_hr !=-1) break;
    hr++;
  } while (hr<24);
  return 0;
} 


















