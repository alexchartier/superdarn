;main program: ctmt_viewer.pro
;reads ctmt_diurnal_2002_2008.nc, ctmt_semidiurnal_2002_2008.nc and
;displays monthly amplitude and phase cross sections
;tested on Mac
;author: Jens Oberheide, Clemson University


;intial settings
pro ctmt_viewer_event,ev
COMMON values, options_id,tmp_path,tmp_fname_diurnal,tmp_fname_semi,intro_out,print_command,print_id,cz0,result_di,result_sd,lat,lev,month,amp_di,phase_di,amp_sd,phase_sd,component,fiel,components,itideselect,minlat,maxlat,minlev,maxlev,yoffset
widget_control, ev.id, get_uvalue=uvalue

CASE uvalue OF
 'quit': BEGIN 
   widget_control, /destroy, ev.top
 END 
 'printps': BEGIN 
  widget_control, /hourglass
  printps
 END  
 'printpscommand': BEGIN
  widget_control,print_id, get_value=print_command
 END
 'saveplot': BEGIN 
  saveplot
 END 
 'tdw2': begin
  if ev.select ne 0 then begin 
   itideselect=0
   redoplot 
  endif
  end
 'tdw1': begin
  if ev.select ne 0 then begin 
   itideselect=1
   redoplot 
  endif
  end
 'tds0': begin
  if ev.select ne 0 then begin 
   itideselect=2
   redoplot 
  endif
  end
 'tde1': begin
  if ev.select ne 0 then begin 
   itideselect=3
   redoplot 
  endif
  end
 'tde2': begin
  if ev.select ne 0 then begin 
   itideselect=4
   redoplot 
  endif
  end
 'tde3': begin
  if ev.select ne 0 then begin 
   itideselect=5
   redoplot 
  endif
  end
 'tsw4': begin
  if ev.select ne 0 then begin 
   itideselect=6
   redoplot 
  endif
  end
 'tsw3': begin
  if ev.select ne 0 then begin 
   itideselect=7
   redoplot 
  endif
  end
 'tsw2': begin
  if ev.select ne 0 then begin 
   itideselect=8
   redoplot 
  endif
  end
 'tsw1': begin
  if ev.select ne 0 then begin 
   itideselect=9
   redoplot 
  endif
  end
 'tss0': begin
  if ev.select ne 0 then begin 
   itideselect=10
   redoplot 
  endif
  end
 'tse1': begin
  if ev.select ne 0 then begin 
   itideselect=11
   redoplot 
  endif
  end
 'tse2': begin
  if ev.select ne 0 then begin 
   itideselect=12
   redoplot 
  endif
  end
 'tse3': begin
  if ev.select ne 0 then begin 
   itideselect=13
   redoplot 
  endif
  end

 'ft': begin
   if ev.select ne 0 then begin
    fiel='t'
    redoplot
   endif
   end
 'fu': begin
   if ev.select ne 0 then begin
    fiel='u'
    redoplot
   endif
   end
 'fv': begin
   if ev.select ne 0 then begin
    fiel='v'
    redoplot
   endif
   end
 'fw': begin
   if ev.select ne 0 then begin
    fiel='w'
    redoplot
   endif
   end
 'fr': begin
   if ev.select ne 0 then begin
    fiel='d'
    redoplot
   endif
   end

 'minlat': begin
  widget_control,ev.id,get_value=getval
  minlat=getval
 end
 'maxlat': begin
  widget_control,ev.id,get_value=getval
  maxlat=getval
 end
 'redrawlat': begin
  redoplot
 end
 'minlev': begin
  widget_control,ev.id,get_value=getval
  minlev=getval
 end
 'maxlev': begin
  widget_control,ev.id,get_value=getval
  maxlev=getval
 end
 'redrawheight': begin
  redoplot
 end
ENDCASE
end

;widget handling for filename/path window
pro intro_event,ev
COMMON values
COMMON opt,path,fname_diurnal,fname_semi
widget_control,ev.id,get_uvalue=uvalue

CASE uvalue OF
 'cancel': Begin
 intro_out=1
 widget_control,options_id,/destroy
END
 'accept': Begin
  intro_out=0
  path=tmp_path
  fname_diurnal=tmp_fname_diurnal
  fname_semi=tmp_fname_semi
  widget_control,options_id,/destroy
END
 'pathfield': Begin
  widget_control,ev.id, get_value=getval
  tmp_path=getval
END
 'difile': Begin
  widget_control,ev.id, get_value=getval
  tmp_fname_diurnal=getval
END
 'sdfile': Begin
  widget_control,ev.id, get_value=getval
  tmp_fname_semi=getval
END
 'tdw2': if ev.select ne 0 then itideselect=0
 'tdw1': if ev.select ne 0 then itideselect=1
 'tds0': if ev.select ne 0 then itideselect=2
 'tde1': if ev.select ne 0 then itideselect=3
 'tde2': if ev.select ne 0 then itideselect=4
 'tde3': if ev.select ne 0 then itideselect=5
 'tsw4': if ev.select ne 0 then itideselect=6
 'tsw3': if ev.select ne 0 then itideselect=7
 'tsw2': if ev.select ne 0 then itideselect=8
 'tsw1': if ev.select ne 0 then itideselect=9
 'tss0': if ev.select ne 0 then itideselect=10
 'tse1': if ev.select ne 0 then itideselect=11
 'tse2': if ev.select ne 0 then itideselect=12
 'tse3': if ev.select ne 0 then itideselect=13

 'ft': if ev.select ne 0 then fiel='t'
 'fu': if ev.select ne 0 then fiel='u'
 'fv': if ev.select ne 0 then fiel='v'
 'fw': if ev.select ne 0 then fiel='w'
 'fr': if ev.select ne 0 then fiel='d'
endcase
end

;filename/path window
pro intro
COMMON values
COMMON opt,path,fname_diurnal,fname_semi
tmp_path=path
tmp_fname_diurnal=fname_diurnal
tmp_fname_semi=fname_semi
options_id=widget_base(/row,title='Initial settings!',group_leader=base_id)
options1_id=widget_base(options_id,/column)
options2_id=widget_base(options_id,/column)
path_field=cw_field(options1_id,title='Directory containing CTMT netcdf files:',/string,$
                    value=tmp_path,uvalue='pathfield',/all_events,/row)
di_field=cw_field(options1_id,title='24h file:',/string,value=tmp_fname_diurnal,uvalue='difile',/all_events,/row)
sd_field=cw_field(options1_id,title='12h file:',/string,value=tmp_fname_semi,uvalue='sdfile',/all_events,/row)

tide_id=widget_base(options1_id,/exclusive,row=2,frame=2)
dw2=widget_button(tide_id,value='DW2',uvalue='tdw2')
dw1=widget_button(tide_id,value='DW1',uvalue='tdw1')
ds0=widget_button(tide_id,value='D0',uvalue='tds0')
de1=widget_button(tide_id,value='DE1',uvalue='tde1')
de2=widget_button(tide_id,value='DE2',uvalue='tde2')
de3=widget_button(tide_id,value='DE3',uvalue='tde3')
sw4=widget_button(tide_id,value='SW4',uvalue='tsw4')
sw3=widget_button(tide_id,value='SW3',uvalue='tsw3')
sw2=widget_button(tide_id,value='SW2',uvalue='tsw2')
sw1=widget_button(tide_id,value='SW1',uvalue='tsw1')
ss0=widget_button(tide_id,value='S0',uvalue='tss0')
se1=widget_button(tide_id,value='SE1',uvalue='tse1')
se2=widget_button(tide_id,value='SE2',uvalue='tse2')
se3=widget_button(tide_id,value='SE3',uvalue='tse3')
widget_control,dw1,set_button=1

field_id=widget_base(options1_id,/exclusive,/row,frame=2)
tf=widget_button(field_id,value='T',uvalue='ft')
uf=widget_button(field_id,value='U',uvalue='fu')
vf=widget_button(field_id,value='V',uvalue='fv')
wf=widget_button(field_id,value='W',uvalue='fw')
rf=widget_button(field_id,value='RHO',uvalue='fr')
widget_control,tf,set_button=1


optionsb_id = widget_base(options1_id, /row, /align_center)
button1_id = widget_button(optionsb_id, value='Accept', uvalue='accept')
button2_id = widget_button(optionsb_id, value='Cancel', uvalue='cancel')
widget_control, options_id, /realize
xmanager, 'intro', options_id
end


;subroutine to plot a colorbar
pro colorbar,minval,maxval,stitle,fillcolor,dx,ystart
COMMON values

dy=0.0125
ys=0.05

ncolors=n_elements(fillcolor)+1
np=ncolors-1

x=[0.1,0.125,0.125,0.1,0.1]
y=[ys,ys,ys+dy,ys+dy,ys]

offset=findgen(ncolors)*0.025

dx=dx-np/2.*0.025-0.1

smaxval=string(maxval,format='(F4.1)')
sminval=string(minval,format='(F4.1)')

case cz0 of
1.: csize=1.5
3.: csize=1.25
endcase

FOR i = 0, (N_ELEMENTS(fillColor) - 1) DO BEGIN
   POLYFILL, x+offset[i]+dx, ystart+y, COLOR = fillColor[i], $
   /norm
 PLOTS, x+offset[i]+dx, ystart+y, /norm
endfor
   xyouts,x(0)+offset(np/2)+dx,ystart+ys+1.5*dy,stitle,/norm,align=0.5,color=0,charsize=csize,charthick=1.5
   xyouts,x(0)+offset(0)+dx,ystart+ys-dy,string(minval,format='(F4.1)'),charsize=csize,align=0,/norm,color=0,charthick=1.5
   xyouts,x(0)+offset(np/2)+dx,ystart+ys-dy,string((minval+maxval)/2,format='(F4.1)'),charsize=csize,align=0.5,/norm,color=0,charthick=1.5
   xyouts,x(0)+offset(np)+dx,ystart+ys-dy,''+string(maxval,format='(F4.1)'),charsize=csize,align=1,/norm,color=0,charthick=1.5

end;colorbar


;read netcdf
pro read_data
COMMON values
COMMON opt

components=['w2','w1','s0','e1','e2','e3','w4','w3','w2','w1','s0','e1','e2','e3']
component=components(itideselect)

if itideselect le 5 then begin

;diurnal
ncid=NCDF_OPEN(result_di(0),/nowrite)

id_lat=NCDF_VARID(ncid,'lat')
NCDF_VARGET,ncid,id_lat,lat
id_lev=NCDF_VARID(ncid,'lev')
NCDF_VARGET,ncid,id_lev,lev
id_month=NCDF_VARID(ncid,'month')
NCDF_VARGET,ncid,id_month,month
id_avar=NCDF_VARID(ncid,'amp_'+component+'_'+fiel)
NCDF_VARGET,ncid,id_avar,afield
id_pvar=NCDF_VARID(ncid,'phase_'+component+'_'+fiel)
NCDF_VARGET,ncid,id_pvar,pfield
NCDF_CLOSE,ncid

nlat=n_elements(lat)
nlev=n_elements(lev)
nmonth=n_elements(month)

amp_di=fltarr(nlat,nlev,nmonth)-999.
phase_di=fltarr(nlat,nlev,nmonth)-999.

for imonth=0,nmonth-1 do begin
 for ilev=0,nlev-1 do begin
   amp_di(*,ilev,imonth)=afield(*,ilev,imonth)
   isbad=where(amp_di(*,ilev,imonth) lt 0.,nisbad)
   phase_di(*,ilev,imonth)=pfield(*,ilev,imonth)
   if nisbad gt 0 then phase_di(isbad,ilev,imonth)=-999.
 endfor
endfor
endif else begin

;semidiurnal
ncid=NCDF_OPEN(result_sd(0),/nowrite)

id_lat=NCDF_VARID(ncid,'lat')
NCDF_VARGET,ncid,id_lat,lat
id_lev=NCDF_VARID(ncid,'lev')
NCDF_VARGET,ncid,id_lev,lev
id_month=NCDF_VARID(ncid,'month')
NCDF_VARGET,ncid,id_month,month
id_avar=NCDF_VARID(ncid,'amp_'+component+'_'+fiel)
NCDF_VARGET,ncid,id_avar,afield
id_pvar=NCDF_VARID(ncid,'phase_'+component+'_'+fiel)
NCDF_VARGET,ncid,id_pvar,pfield
NCDF_CLOSE,ncid

nlat=n_elements(lat)
nlev=n_elements(lev)
nmonth=n_elements(month)

amp_sd=fltarr(nlat,nlev,nmonth)-999.
phase_sd=fltarr(nlat,nlev,nmonth)-999.

for imonth=0,nmonth-1 do begin
 for ilev=0,nlev-1 do begin
   amp_sd(*,ilev,imonth)=afield(*,ilev,imonth)
   isbad=where(amp_sd(*,ilev,imonth) lt 0.,nisbad)
   phase_sd(*,ilev,imonth)=pfield(*,ilev,imonth)
   if nisbad gt 0 then phase_sd(isbad,ilev,imonth)=-999.
 endfor
endfor
endelse
end



;contour plot routine
pro redoplot
COMMON values
COMMON display,color0,black,white,ncolors,draw_id
COMMON opt

if minlat ge maxlat then begin
 result=dialog_message('MAXLAT > MINLAT REQUIRED, TRY AGAIN',/center,/error)
 goto,end_redoplot
endif

if (minlat gt 90 and maxlat gt 90) or (minlat lt -90 and maxlat lt -90) then begin
 result=dialog_message('NO LATS WITHIN +-90 DEG SELECTED, TRY AGAIN',/center,/error)
 goto,end_redoplot
endif

if minlev ge maxlev then begin
 result=dialog_message('MAXLEV > MINLEV REQUIRED, TRY AGAIN',/center,/error)
 goto,end_redoplot
endif

if (minlev gt 400 and maxlev gt 400) or (minlev lt 0 and maxlev lt 0) then begin
 result=dialog_message('NO HEIGHTS WITHIN 0-400 KM SELECTED, TRY AGAIN',/center,/error)
 goto,end_redoplot
endif

color0 = 39
ctable = color0
loadct, ctable, /silent
tvlct, r, g, b, /get
ncolors = n_elements(r)
r(0) = 0 & g(0)=0 & b(0)=0
r(ncolors-1) = 255 & g(ncolors-1)=255 & b(ncolors-1)=255
tvlct, r, g, b
white = ncolors-1
black = 0

!P.Background=white
fcolor=[31,47,95,124,150,177,191,199,211,254]
fpcolor=[15,31,47,79,95,124,150,177,191,199,211,254]

read_data
di=0
sd=0
if itideselect le 5 then di=1
if itideselect gt 5 then sd=1

if di eq 1 then begin
 amp=amp_di
 phase=phase_di
endif
if sd eq 1 then begin
 amp=amp_sd
 phase=phase_sd
endif
 

;height plots
minalt=minlev
maxalt=maxlev

isalt=where(lev ge minalt and lev le maxalt,nisalt)
islat=where(lat ge minlat and lat le maxlat)

is1=where(lev eq minalt,nis1)
is2=where(lev eq maxalt,nis2)

if nis1 eq 0 and lev(isalt(0)) ne 0. then isalt=[isalt(0)-1,isalt]
nisalt=n_elements(isalt)

if nis2 eq 0 and lev(isalt(nisalt-1)) ne 400. then isalt=[isalt,isalt(nisalt-1)+1]

smonth=['Jan','Feb','Mar','Apr','May',$
'Jun','Jul','Aug','Sep','Oct','Nov','Dec']

if component eq 's0' then component='0'

if di eq 1 then scomp='d'+component
if sd eq 1 then scomp='s'+component
scomp=strupcase(scomp)
wind=strupcase(fiel)
ampunit='(m/s)'
if wind eq 'T' then ampunit='(K)'
if wind eq 'D' then ampunit='(%)'
if wind eq 'W' then ampunit='(cm/s)'
if wind eq 'D' then wind='Density'

if wind eq 'Density' then amp=amp*100.
if wind eq 'W' then amp=amp*100.
maxamp=max(amp(islat,isalt,*))
minamp=min(amp(islat,isalt,*))

levels=0.*maxamp/10.+findgen(11)/10.*maxamp
levels=minamp+findgen(11)/10.*(maxamp-minamp)
if di eq 1 then plevels=findgen(13)/12.*24.
if sd eq 1 then plevels=findgen(13)/12.*12.


for im=0,3 do begin
if im eq 0 then yc=1 else yc=0.0000001
if im eq 0 then noer=0 else noer=1
contour,amp(*,*,im),lat,lev,levels=levels,/xstyle,/ystyle,$
 yrange=[minalt,maxalt],xrange=[minlat,maxlat],ytitle='Altitude [km]',ycharsize=yc,c_charsize=0.75,$
charthick=1.5,c_thick=1.5,c_charthick=3,position=[0.09+0.23*im,0.87+yoffset,0.29+0.23*im,0.95+yoffset],$
/cell_fill,/color, c_color=fcolor,min_val=0.,title=smonth(im),noerase=noer;,$

contour,amp(*,*,im),lat,lev,levels=levels,c_charsize=0.00001,$
min_val=0.,/overplot
endfor

;xyouts,0.5,0.96, scomp+', '+strupcase(wind)+', AMPLITUDE',align=0.5,/normal,charsize=1.5,charthick=cz0,color=black

for im=0,3 do begin
if im eq 0 then yc=1 else yc=0.0000001
contour,amp(*,*,im+4),lat,lev,levels=levels,/xstyle,/ystyle,$
 yrange=[minalt,maxalt],xrange=[minlat,maxlat],ytitle='Altitude [km]',ycharsize=yc,c_charsize=0.75,$
charthick=1.5,c_thick=1.5,c_charthick=3,position=[0.09+0.23*im,0.74+yoffset,0.29+0.23*im,0.82+yoffset],$
/cell_fill,/color, c_color=fcolor,min_val=0.,title=smonth(im+4),/noerase;,$

contour,amp(*,*,im+4),lat,lev,levels=levels,c_charsize=0.00001,$
min_val=0.,/overplot
endfor

for im=0,3 do begin
if im eq 0 then yc=1 else yc=0.0000001
contour,amp(*,*,im+8),lat,lev,levels=levels,/xstyle,/ystyle,$
 yrange=[minalt,maxalt],xrange=[minlat,maxlat],ytitle='Altitude [km]',ycharsize=yc,c_charsize=0.75,$
charthick=1.5,c_thick=1.5,c_charthick=3,position=[0.09+0.23*im,0.61+yoffset,0.29+0.23*im,0.69+yoffset],$
/cell_fill,/color, c_color=fcolor,min_val=0.,title=smonth(im+8),/noerase,xtitle='Latitude [deg]';,$

contour,amp(*,*,im+8),lat,lev,levels=levels,c_charsize=0.00001,$
min_val=0.,/overplot
endfor

colorbar,minamp,maxamp,scomp+' '+wind+' Amplitude '+ampunit,fcolor,0.5,0.48+yoffset


for im=0,3 do begin
if im eq 0 then yc=1 else yc=0.0000001
contour,phase(*,*,im),lat,lev,levels=plevels,/xstyle,/ystyle,$
 yrange=[minalt,maxalt],xrange=[minlat,maxlat],ytitle='Altitude [km]',ycharsize=yc,c_charsize=0.75,$
charthick=1.5,c_thick=1.5,c_charthick=3,position=[0.09+0.23*im,0.4+yoffset,0.29+0.23*im,0.48+yoffset],$
/cell_fill,/color, c_color=fpcolor,min_val=0.,title=smonth(im),/noerase;,$

contour,phase(*,*,im),lat,lev,levels=plevels,c_charsize=0.00001,$
min_val=0.,/overplot
endfor



for im=0,3 do begin
if im eq 0 then yc=1 else yc=0.0000001
contour,phase(*,*,im+4),lat,lev,levels=plevels,/xstyle,/ystyle,$
 yrange=[minalt,maxalt],xrange=[minlat,maxlat],ytitle='Altitude [km]',ycharsize=yc,c_charsize=0.75,$
charthick=1.5,c_thick=1.5,c_charthick=3,position=[0.09+0.23*im,0.27+yoffset,0.29+0.23*im,0.35+yoffset],$
/cell_fill,/color, c_color=fpcolor,min_val=0.,title=smonth(im+4),/noerase;,$

contour,phase(*,*,im+4),lat,lev,levels=plevels,c_charsize=0.00001,$
min_val=0.,/overplot
endfor

for im=0,3 do begin
if im eq 0 then yc=1 else yc=0.0000001
contour,phase(*,*,im+8),lat,lev,levels=plevels,/xstyle,/ystyle,$
 yrange=[minalt,maxalt],xrange=[minlat,maxlat],ytitle='Altitude [km]',ycharsize=yc,c_charsize=0.75,$
charthick=1.5,c_thick=1.5,c_charthick=3,position=[0.09+0.23*im,0.14+yoffset,0.29+0.23*im,0.22+yoffset],$
/cell_fill,/color, c_color=fpcolor,min_val=0.,title=smonth(im+8),/noerase,xtitle='Latitude [deg]';,$

contour,phase(*,*,im+8),lat,lev,levels=plevels,c_charsize=0.00001,$
min_val=0.,/overplot
endfor

colorbar,min(plevels),max(plevels),scomp+' '+wind+' Phase (UT of max)',fpcolor,0.5,0.01+yoffset

end_redoplot:

end


;write plot into postscript
PRO saveplot
 COMMON display
 COMMON values

  plot_file = dialog_pickfile(filter='*.ps', title='PLOT FILE TO BE SAVED')
  check = findfile(plot_file, count=c)
  IF plot_file EQ '' THEN return
   if(c ne 0) then begin
     answer = dialog_message('File exists.  Overwrite?', /question)
     if(answer eq 'No') then return
   endif

  set_plot, 'ps'
 !P.Font=1
 a4long		= 29.7 ; cm
 a4short		= 21.0 ; cm

 IF ( N_ELEMENTS(shortoffset) LE 0) THEN shortoffset = 4./2. ; cm
 IF ( N_ELEMENTS(longoffset) LE 0 ) THEN longoffset  = 3.5/2. ; cm

 shortside = a4short-shortoffset-1.8 ; cm
 longside  = a4long -longoffset -1.0 ; cm
 shortoffset = (a4short-shortside)/2;   -1.8 ; cm
 longoffset = (a4long-longside)/2   ;   -4.0 ; cm

 device, XSIZE=shortside, YSIZE=longside, $
  XOFF=shortoffset, YOFF=longoffset, /color,filename=plot_file,encapsu=0
  yoffset=0.
  cz0 = 3.
  redoplot
  device, /close
  set_plot, 'x'
  !P.Font=-1
  cz0 = 1.
  yoffset=0.0
 return 
END 


;unix print command
PRO printps;print output
 COMMON display
 COMMON values

 set_plot, 'ps'
 !P.Font=1
 a4long		= 29.7 ; cm
 a4short		= 21.0 ; cm

 IF ( N_ELEMENTS(shortoffset) LE 0) THEN shortoffset = 4./2. ; cm
 IF ( N_ELEMENTS(longoffset) LE 0 ) THEN longoffset  = 3.5/2. ; cm

 shortside = a4short-shortoffset-1.8 ; cm
 longside  = a4long -longoffset -1.0 ; cm
 shortoffset = (a4short-shortside)/2;   -1.8 ; cm
 longoffset = (a4long-longside)/2   ;   -4.0 ; cm

 device, XSIZE=shortside, YSIZE=longside, $
  XOFF=shortoffset, YOFF=longoffset, /color,filename='print.ps',encapsu=0


 cz0 = 3.
 yoffset=0.
 redoplot
 device, /close
 set_plot, 'x'
 !P.Font=-1
 print, 'File saved as print.ps and sent with: '+print_command+' print.ps'
 spawn, print_command+' print.ps'
 cz0 = 1.
; spawn, 'rm print.ps'
 ctable = color0
 yoffset=0.0

END 


;main program
pro ctmt_viewer
COMMON opt
COMMON values
COMMON display
;graphics
;set color table
 device, true_color=24; for Mac


;pre-select
itideselect=1;DW1
fiel='t'
minlat=-90.
maxlat=90.
minlev=50.
maxlev=400.
minlev=80.
maxlev=150.
cz0=1.
yoffset=0.0

;inital path
path='./'
fname_diurnal='ctmt_diurnal_2002_2008.nc'
fname_semi='ctmt_semidiurnal_2002_2008.nc'

fcheck:
;intro
;if intro_out eq 1 then goto, end_of_code
;check if files exists
result_di=file_search(path+fname_diurnal,count=count_di,/fully_qualify_path)
result_sd=file_search(path+fname_semi,count=count_sd,/fully_qualify_path)
if count_di eq 0 or count_sd eq 0 then begin
 intro
 if intro_out eq 1 then goto, end_of_code
 result_di=file_search(path+fname_diurnal,count=count_di,/fully_qualify_path)
 result_sd=file_search(path+fname_semi,count=count_sd,/fully_qualify_path)
endif
if count_di eq 0 or count_sd eq 0 then begin
result=dialog_message('File name(s) and/or path incorrect!',/center,/error)
goto,fcheck
endif

;base widget
base_id = widget_base(/row, title='Climatological Tidal Model of the Thermosphere (CTMT)')

;draw window
device,decomposed=0, get_screen_size=screen_size
; ctable = 39
 color0 = 39
 ctable = color0
 loadct, ctable, /silent
 tvlct, r, g, b, /get
 ncolors = n_elements(r)
 r(0) = 0 & g(0)=0 & b(0)=0
 r(ncolors-1) = 255 & g(ncolors-1)=255 & b(ncolors-1)=255
 tvlct, r, g, b
 white = ncolors-1
 black = 0

!P.Background=white
device,get_screen_size=test
test=test;*0.75
 draw_id = widget_draw(base_id, xsize=test(0)*0.75, ysize=test(1)*0.9)

;open/save/print/settings/quit
 base3_id = widget_base(base_id, /column)

 button_id = widget_button(base3_id, value='SAVE PLOT AS PS', uvalue='saveplot')
 button_id = widget_button(base3_id, value='PRINT PLOT AS PS', uvalue='printps')
 button_id = widget_button(base3_id, value='QUIT', uvalue='quit')

;print command
 base4_id=widget_base(base3_id,/column,frame=2)
 print_command='lpr -Pncl2'
 label_id = widget_label(base4_id, value='PRINT COMMAND', /align_center)
 print_id = widget_text(base4_id, value=print_command, /editable, /align_center, uvalue='printpscommand', /all_events)
 widget_control, print_id, get_value=print_command

;Fields
test_id=widget_base(base3_id,/column,frame=2)
label2_id=widget_label(test_id,value='COMPONENTS',/align_center)
tide_id=widget_base(test_id,/exclusive,column=2)
dw2=widget_button(tide_id,value='DW2',uvalue='tdw2')
dw1=widget_button(tide_id,value='DW1',uvalue='tdw1')
ds0=widget_button(tide_id,value='D0',uvalue='tds0')
de1=widget_button(tide_id,value='DE1',uvalue='tde1')
de2=widget_button(tide_id,value='DE2',uvalue='tde2')
de3=widget_button(tide_id,value='DE3',uvalue='tde3')
sw4=widget_button(tide_id,value='SW4',uvalue='tsw4')
sw3=widget_button(tide_id,value='SW3',uvalue='tsw3')
sw2=widget_button(tide_id,value='SW2',uvalue='tsw2')
sw1=widget_button(tide_id,value='SW1',uvalue='tsw1')
ss0=widget_button(tide_id,value='S0',uvalue='tss0')
se1=widget_button(tide_id,value='SE1',uvalue='tse1')
se2=widget_button(tide_id,value='SE2',uvalue='tse2')
se3=widget_button(tide_id,value='SE3',uvalue='tse3')

case itideselect of
 0: widget_control,dw2,set_button=1
 1: widget_control,dw1,set_button=1
 2: widget_control,ds0,set_button=1
 3: widget_control,de1,set_button=1
 4: widget_control,de2,set_button=1
 5: widget_control,de3,set_button=1
 6: widget_control,sw4,set_button=1
 7: widget_control,sw3,set_button=1
 8: widget_control,sw2,set_button=1
 9: widget_control,sw1,set_button=1
 10: widget_control,ss0,set_button=1
 11: widget_control,se1,set_button=1
 12: widget_control,se2,set_button=1
 13: widget_control,se3,set_button=1
endcase


test2_id=widget_base(base3_id,/column,frame=2)
label_id=widget_label(test2_id,value='FIELDS',/align_center)
field_id=widget_base(test2_id,/exclusive,column=2)
tf=widget_button(field_id,value='T',uvalue='ft')
uf=widget_button(field_id,value='U',uvalue='fu')
vf=widget_button(field_id,value='V',uvalue='fv')
wf=widget_button(field_id,value='W',uvalue='fw')
rf=widget_button(field_id,value='RHO',uvalue='fr')
case fiel of 
 't': widget_control,tf,set_button=1
 'u': widget_control,uf,set_button=1
 'v': widget_control,vf,set_button=1
 'w': widget_control,wf,set_button=1
 'd': widget_control,rf,set_button=1
endcase


;lat range
 base5_id=widget_base(base3_id,/column,frame=2)
 label_id = widget_label(base5_id, value='LATITUDE RANGE', /align_center)
 label_id = widget_label(base5_id, value='(-90 TO +90 DEG)',/align_center)
 lat_field1=cw_field(base5_id,title='MIN',/floating,value=minlat,uvalue='minlat',/all_events)
 lat_field2=cw_field(base5_id,title='MAX',/floating,value=maxlat,uvalue='maxlat',/all_events)
 button_id = widget_button(base5_id, value='REDRAW', uvalue='redrawlat')



;height range
 base6_id=widget_base(base3_id,/column,frame=2)
 label_id = widget_label(base6_id, value='HEIGHT RANGE', /align_center)
 label_id = widget_label(base6_id, value='(0 TO 400 KM)',/align_center)
 z_field1=cw_field(base6_id,title='MIN',/floating,value=minlev,uvalue='minlev',/all_events)
 z_field2=cw_field(base6_id,title='MAX',/floating,value=maxlev,uvalue='maxlev',/all_events)
 button_id = widget_button(base6_id, value='REDRAW', uvalue='redrawheight')


; realize widget
widget_control, base_id, /realize

;do initial plot
 redoplot

;register widget
 xmanager, 'ctmt_viewer', base_id, group=group, /no_block

end_of_code:
end
