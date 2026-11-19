set defa to /datos/guias
set stat off
set cent on
set date ansi
set talk off
set dele on
set safe off
clos data

use /u/admin2/ordenes
go bott
word_ini=nro_orden
word_fin=nro_orden
worden=str(word_ini,6)
wper=subs(dtos(date()+1),3,4)
wper="2601"
do while .t.
   clos data
   clear 
   @0,0 say "SERVILLA S.A."
   @1,0 say "Actualizando de datos con el corte anterior"
   @2,0 TO 2,79
   @4,0 say "Periodo " get wper pict "9999"
   @6,0 say "Numero de Orden Inicial:" get word_ini pict "999999"
   @6,col()+2 say "y Final " get word_fin pict "999999"
   read
   if word_ini=0.or.read()=12.or.read()=4
      clos data
      set defa to /u/admin2
      return
   endif
   whis="guia"+allt(wper)+".his"
   worden_i=str(word_ini,6)
   worden_f=str(word_fin,6)
   worden=worden_i
   if .not. file(whis)
       do aviso with "Periodo Historico no existe !!!"
       loop
   else
       use &whis orde orden shared
       if seek(worden_i)
          if seek(worden_f)
             do busqueda
             loop
          endif
       endif
       do aviso with "Revise los numeros de orden !!"
       loop
   endif
enddo

******************
PROCEDURE BUSQUEDA
******************
do abrir_periodos
sele 1
set orde to 4
SEEK worden_i
wveces=1
wdir_esp=0
wcas_cor=0
wcas_dev=0
wcas_aju=0
wsin_sec=0
west_his=0
wrut_dir=0
do while a.orden<=worden_f
   @11,3 say a.orden+","+a.serial+","+str(wveces)+" #:"+a.secuencia
   sele 2
   seek a.no_entidad+a.identdes +a.nombred
   sele 3
   seek a.no_entidad+a.identdes +a.nombred
  
   sele 1
   do while .t.
      if rlock()
         do trabajo
         @13,10 say "Estados Historicos    "+tran(west_his,"999,999")
         @14,10 say "RUTAS encontradas     "+tran(wrut_dir,"999,999")
         @15,10 say "Direcciones Especiales"+tran(wdir_esp,"999,999")
         @16,10 say "Direcciones Corregidas"+tran(wcas_cor,"999,999")
         @17,10 say "Devoluciones Marcadas "+tran(wcas_dev,"999,999")
         @18,10 say "Ajustes  de  Sector   "+tran(wcas_aju,"999,999")
         @19,10 say "Registros SIN Sector  "+tran(wsin_sec,"999,999")
         exit
      endif
   enddo
   select 1
   skip
   if eof()
      exit
   endif
enddo
clos data
use /u/admin2/ordenes_ orde 1
seek word_ini
if .not. found()
   sele 2
   use /u/admin2/ordenes orde 1
   seek word_ini
   copy to /u/tmp/orden1.tmp next 1
   use
   sele 1
   appe from /u/tmp/orden1.tmp
endif
seek word_ini
repl q_est_his with west_his,;
     q_rutas   with wrut_dir,;
     q_dir_esp with wdir_esp,;
     q_correci with wcas_cor,;
     q_devoluc with wcas_dev,;
     q_ajustes with wcas_aju,;
     q_sin_sec with wsin_sec next 1
clos data


set defa to /datos/guias
if wper="2601"
   do pegado01
endif
if wper="8853"
   do pegado53
endif
if wper="8851"
   do pegado51
endif

set orde to 4
************************************************************************
*** PUNTO 1 - ajuste 15/10/2026: direccion ajustada + dir_num del ERP
*** Las guias SIN digitos en dir_num se envian al servidor web
*** (dirnum_sco.py), que devuelve la direccion ajustada y el dir_num con
*** la logica de erp.servilla.com.co/direcciones. Despues corren las
*** REGLAS DE DEVOLUCION de siempre. Respaldo: arrastre_antes_dirnum.prg
************************************************************************
do punto1_dirnum
sele 1
set orde to 4
?"...Buscando + Devoluciones"

************************************************************************
*** REGLAS DE DEVOLUCION - ajuste 08/10/2026
*** Se marca solo si el MISMO tipo de devolucion esta en AMBOS meses
*** (antepenultimo: est_his 3-8, penultimo: est_his 12-17) y no hay
*** E50 en ningun mes. Guias sin ningun digito en dir_num y sin E50 -> *DEV_21
*** Las reglas anteriores estan en arrastre_reglas_viejas.prg
************************************************************************
WLLAVE=STR(word_ini,6)+"i"

seek WLLAVE
repl cod_sec with "*DEV_ 1" while orden+retorno=wllave ;
	FOR "D 1"$subs(est_his,3,6).and."D 1"$subs(est_his,12,6).and..not."E50"$est_his.and.cod_sec<>"*"

seek WLLAVE
repl cod_sec with "*DEV_ 2" while orden+retorno=wllave ;
	FOR "D 2"$subs(est_his,3,6).and."D 2"$subs(est_his,12,6).and..not."E50"$est_his.and.cod_sec<>"*"

seek WLLAVE
repl cod_sec with "*DEV_ 5" while orden+retorno=wllave ;
	FOR "D 5"$subs(est_his,3,6).and."D 5"$subs(est_his,12,6).and..not."E50"$est_his.and.cod_sec<>"*"

seek WLLAVE
repl cod_sec with "*DEV_17" while orden+retorno=wllave ;
	FOR "D17"$subs(est_his,3,6).and."D17"$subs(est_his,12,6).and..not."E50"$est_his.and.cod_sec<>"*"

seek WLLAVE
repl cod_sec with "*DEV_21" while orden+retorno=wllave ;
	FOR "D21"$subs(est_his,3,6).and."D21"$subs(est_his,12,6).and..not."E50"$est_his.and.cod_sec<>"*"

seek WLLAVE
repl cod_sec with "*DEV_22" while orden+retorno=wllave ;
	FOR "D22"$subs(est_his,3,6).and."D22"$subs(est_his,12,6).and..not."E50"$est_his.and.cod_sec<>"*"

*** Sin numero en dir_num y sin E50 en ningun mes
seek WLLAVE
repl cod_sec with "*DEV_21" while orden+retorno=wllave ;
	FOR empty(chrtran(dir_num,chrtran(dir_num,"0123456789",""),"")).and..not."E50"$est_his.and.cod_sec<>"*"

************************************************************************
*** NIVEL EXTRA **** l-i *** Sirve para el Cierre (mismas reglas)
************************************************************************
set orde to rutas
wllave2=worden+"il"

seek WLLAVE2
repl cod_sec with "*DEV_ 1" while orden+ret_esc+retorno=wllave2 ;
	FOR "D 1"$subs(est_his,3,6).and."D 1"$subs(est_his,12,6).and..not."E50"$est_his.and.cod_sec<>"*"

seek WLLAVE2
repl cod_sec with "*DEV_ 2" while orden+ret_esc+retorno=wllave2 ;
	FOR "D 2"$subs(est_his,3,6).and."D 2"$subs(est_his,12,6).and..not."E50"$est_his.and.cod_sec<>"*"

seek WLLAVE2
repl cod_sec with "*DEV_ 5" while orden+ret_esc+retorno=wllave2 ;
	FOR "D 5"$subs(est_his,3,6).and."D 5"$subs(est_his,12,6).and..not."E50"$est_his.and.cod_sec<>"*"

seek WLLAVE2
repl cod_sec with "*DEV_17" while orden+ret_esc+retorno=wllave2 ;
	FOR "D17"$subs(est_his,3,6).and."D17"$subs(est_his,12,6).and..not."E50"$est_his.and.cod_sec<>"*"

seek WLLAVE2
repl cod_sec with "*DEV_21" while orden+ret_esc+retorno=wllave2 ;
	FOR "D21"$subs(est_his,3,6).and."D21"$subs(est_his,12,6).and..not."E50"$est_his.and.cod_sec<>"*"

seek WLLAVE2
repl cod_sec with "*DEV_22" while orden+ret_esc+retorno=wllave2 ;
	FOR "D22"$subs(est_his,3,6).and."D22"$subs(est_his,12,6).and..not."E50"$est_his.and.cod_sec<>"*"

*** Sin numero en dir_num y sin E50 en ningun mes
seek WLLAVE2
repl cod_sec with "*DEV_21" while orden+ret_esc+retorno=wllave2 ;
	FOR empty(chrtran(dir_num,chrtran(dir_num,"0123456789",""),"")).and..not."E50"$est_his.and.cod_sec<>"*"

************************************************
		
seek worden
sum 1 for cod_sec="*" to wnum_dev while orden=worden 

?"  Devoluciones encontradas:",tran(wnum_dev,"9,999")
set defa to /u/admin2
clos data
@23,24 say "*** FIN DEL TRABAJO ***"
READ

************************
PROCEDURE abrir_periodos
************************
wsfec=wper
warcgm="guia"+wsfec+".his"
warcgi="guia"+wsfec+".ind"
wndxgui=""
sele 19
use /datos/guias/&warcgi shared
set filt to foxplus
go top
do while .not. eof()
   wndxgui=wndxgui+ltrim(rtrim(archivo))+","
   skip
enddo
wndxgui=subs(wndxgui,1,len(wndxgui)-1)
set path to &rutaguia
sele 1
use &warcgm shared
set inde to &wndxgui
set path to
do case
   case wper="8853".or.wper="8833".or.wper="8854"
        sele 2
        use guia8863.his inde 8863no_e && antpenult
        sele 3
        use guia8873.his inde 8873no_e && penultimo
   case wper="8852"
        sele 2
        use guia8862.his inde 8862no_e && antpenult
        sele 3
        use guia8872.his inde 8872no_e && penultimo
   case wper="8851"
        sele 2
        use guia8861.his inde 8861no_e && antepenultimo
        sele 3
        use guia8871.his inde 8871no_e && penultimo
   other
        sele 19
        use serial orde 2
        seek wper
        skip -1
        wper_ant=periodo
        sele 3
        whis="guia"+wper_ant+".his"
        wind=wper_ant+"no_e"
        use &whis inde &wind
        sele 19
        skip -1
        wper_pen=periodo
        sele 2
        whis="guia"+wper_pen+".his"
        wind=wper_pen+"no_e"
        use &whis inde &wind
endcase
sele 4
use /u/admin2/ordenes orde 1
seek word_ini
@8,0 say ENTIDAD+SERVICIO
@8,30 say "Periodo Penultimo:"+dbf(2)
@9,0 say "Cantidad "+str(cantidad,6)
@9,30 say "      y   Ultimo: "+dbf(3)
sele 5
use /u/admin2/retorno/lote_apl orde no_entidad
sele 6
use /u/admin2/dir_esp
sele 7
use /u/archivos/bas_eje orde 2
sele 8
use /datos/guias/arrastre.his orde serial
sele 11
use /u/admin2/def_sect orde cod_Sec_
sele 12
use /u/admin2/tab_est orde 1
return

*****************
PROCEDURE TRABAJO
*****************
*** ESTADO HISTORICO ***
SELECT 1
repl a.est_his with ;
     subs(dtos(b.f_emi),5,2)+;
     b.retorno+b.cod_mot+;
     b.ret_esc+b.cod_esc+;
     iif(a.dirdes1=b.dirdes1,"=",iif(b.dirdes1=spac(10)," ","#"))+;
     subs(dtos(c.f_emi),5,2)+;
     c.retorno+c.cod_mot+;
     c.ret_esc+c.cod_esc+;
     iif(a.dirdes1=c.dirdes1,"=",iif(c.dirdes1=spac(10)," ","#")) next 1
     if len(allt(a.est_his))>3
        west_his=west_his+1
    endif
if cod_Sec="_EXCLUIR".or.cod_Sec="_VIP".or.cod_Sec="*DEV_INI"
   return
endif

**** RUTAS ***
sele 7 
seek a.ciudad1+subs(a.cod_Sec,1,6)+subs(a.dirdes1,1,at(" ",a.dirdes1,3))
sele 1
*repl ruta with g.ruta next 1
@14,40 say ruta
if len(allt(a.ruta))>1
   wrut_dir=wrut_dir+1
endif

**** Direcciones Especiales

sele 6 
loca for allt(upper(dirdes1))$upper(a.dirdes1).and.len(allt(dirdes1))>8
if found()
   sele 1
   repl barrd2 with cod_sec,;
        cod_Sec with f.cod_Sec,;
        entidad with "*VIP" next 1
   wdir_esp=wdir_esp+1
   RETURN
else
   sele 1
   if mot_esp="VI" 
      repl entidad with "*VIP" NEXT 1
   endif
endif

*** ESPECIALES POR CUENTA o SERIAL ***
sele 1 && 
*if mot_esp<>"  ".and.cod_Sec<>"_VIP"
*   repl barrd2 with cod_sec,cod_Sec with "_VIP" NEXT 1
*   wdir_esp=wdir_esp+1
*   RETURN
*endif

*** CORRECIONES ***
if ordenes.t_dir_cor="T"
   if a.ciudad1="BOGOT".or.a.ciudad1="SOACHA".or.a.retorno="i"
      sele 5
      seek subs(a.no_Entidad,1,20)+"c"+a.identdes+subs(a.nombred,1,15)
      if found().and.a.dirdes1=e.a_dirdes1
          sele 1      
          wsec_ini=cod_Sec
          repl a.dirdes2 with e.dirdes2,;
          a.cod_Sec with e.cod_Sec next 1
          sele 7
          seek a.ciudad1+subs(a.cod_Sec,1,6)+subs(a.dirdes2,1,at(" ",a.dirdes2,3))
          sele 1
          if len(allt(ruta))>1
             wrut_dir=wrut_dir-1
          endif
          repl a.ruta with g.ruta next 1
          if len(allt(ruta))>1
             wrut_dir=wrut_dir+1
          endif
	      do adiciona with "COR"
          sele 1
          wcas_cor=wcas_cor+1
          RETURN
      ENDIF
   ENDIF
ENDIF

*** DEVOLUCIONES ***
if a.retorno="i"
   sele 12
   seek subs(a.est_his,3,7)+subs(a.est_his,12,7)
   if found().and.a.dpto2=spac(5)
      if tipo<>spac(10)
         wclase=clase
         wtipo=tipo
         wsec_ini=a.cod_Sec
         wopcion1=allt(codigo1)
         &wopcion1
         do adiciona with wclase
         wcas_dev=wcas_dev+1
      endif
   endif
endif

*** AJUSTES ***
*** mes anterior *** 
****do while .t.
***   exit
**** +++
wajuste=.f.

sele 11
seek a.cod_Sec
IF ARRASTRE
   sele 1
if a.ciudad1="BOGOT".or.a.ciudad1="SOACHA".or.a.retorno="i"
   if a.cod_Sec<>c.cod_Sec.and.a.cod_Sec<>"*"
      if a.dir_ori<>"   "
         if a.dir_ori=c.dir_ori.and.c.cod_Sec<>"_VIP"
            if c.cod_sec<>"_EXCLUIR"
               sele 1
			   wsec_ini=cod_Sec
			   repl a.cod_Sec with c.cod_Sec next 1
			   do adiciona with "AJU"
			   wajuste=.t.
               wcas_aju=wcas_aju+1
            endif
         endif
      else
         if a.dirdes1=c.dirdes1.and.c.cod_Sec<>"_VIP"
            if c.cod_sec<>"_EXCLUIR"
               sele 1
			   wsec_ini=cod_Sec
			   repl a.cod_SEc with c.cod_Sec next 1
			   do adiciona with "AJU"
			   wajuste=.t.			   
               wcas_aju=wcas_aju+1
            endif
         endif
      endif
   endif

   sele 7
   if val(ruta)>0
      wrut_dir=wrut_dir-1
   endif
   seek a.ciudad1+subs(a.cod_sec,1,6)+subs(a.dirdes1,1,at(" ",a.dirdes1,3))
   sele 1
   repl a.ruta with g.ruta next 1
   if val(ruta)>0
      wrut_dir=wrut_dir+1
   endif
   if a.cod_sec=spac(10)
      wsin_sec=wsin_sec+1
   endif
endif
ELSE
wajuste=.t.
ENDIF

*** mes mas anterior *** 
IF .not. wajuste
if a.ciudad1="BOGOT".or.a.ciudad1="SOACHA".or.a.retorno="i"
   if a.cod_Sec<>b.cod_Sec.and.a.cod_Sec<>"*"
      if a.dir_ori<>"   "
         if a.dir_ori=b.dir_ori.and.b.cod_Sec<>"_VIP"
            if b.cod_sec<>"_EXCLUIR"
               sele 1
			   wsec_ini=cod_Sec
			   repl a.cod_Sec with b.cod_Sec next 1
			   do adiciona with "AJU"
               wcas_aju=wcas_aju+1
            endif
         endif
      else
         if a.dirdes1=b.dirdes1.and.b.cod_Sec<>"_VIP"
            if b.cod_sec<>"_EXCLUIR"
               sele 1
			   wsec_ini=cod_Sec
			   repl a.cod_SEc with b.cod_Sec next 1
			   do adiciona with "AJU"
               wcas_aju=wcas_aju+1
            endif
         endif
      endif
   endif

   sele 7
   if val(ruta)>0
      wrut_dir=wrut_dir-1
   endif
   seek a.ciudad1+subs(a.cod_sec,1,6)+subs(a.dirdes1,1,at(" ",a.dirdes1,3))
   sele 1
   repl a.ruta with g.ruta next 1
   if val(ruta)>0
      wrut_dir=wrut_dir+1
   endif
   if a.cod_sec=spac(10)
      wsin_sec=wsin_sec+1
   endif
endif
ENDIF
*****
***ENDDO
SELECT 1
UNLOCK
wveces=wveces+1
return

***************
PROCEDURE AVISO
***************
parame avi_gen
@11,1 to 11,79
@11,(80-len(avi_gen))/2 say " "+avi_gen+" " color gr+*
@row(),col() say ""
??chr(7)+chr(7)
read
@11,1 to 11,79 clear


******************
PROCEDURE ADICIONA
******************
parame wtip_ope
sele 8
seek wtip_ope+a.serial
if .not.found()
    appen blank
    repl  tipo with wtip_ope,         serial   with a.serial,;
         no_entidad with a.no_Entidad,orden    with a.orden,;
         f_emi   with a.f_emi,        identdes with a.identdes,;
         nombred with a.nombred,      dirdes1  with a.dirdes1,;
         ciudad1 with a.ciudad1,      cod_sec  with wsec_ini,;
         est_his with a.est_his,      nro_imp_g with 1,;
         lote    with e.lote,         f_ret     with e.f_ret,;
         dirdes2 with e.dirdes2,      ciudad2   with e.ciudad1,;
         sec_cor with e.cod_Sec,      f_pro     with e.f_pro,;
         h_pro   with e.h_pro,        orden_a   with e.orden,;
         paso    with 2 next 1
    flush
  endif
sele 1
return


*************************
PROCEDURE PUNTO1_DIRNUM
*************************
*** Ida y vuelta con el servidor web por /u/tmp:
***   dn_<orden>.req  "serial","dirdes1","dir_ori"   (lo deja este programa)
***   dn_<orden>.ok   "serial","dirdes1","dir_num"   (lo deja dirnum_sco.py)
*** Si el servidor web no responde en 2 minutos sigue sin ajuste, como antes.
private wbase,wreq,wtmq,wok,wnum,waju,wini
wbase="/u/tmp/dn_"+allt(worden_i)
wreq=wbase+".req"
wtmq=wbase+".tmq"
wok=wbase+".ok"
if file(wok)
   erase &wok
endif
sele 1
set orde to 4
seek worden_i
count to wnum while orden<=worden_f ;
   for empty(chrtran(dir_num,chrtran(dir_num,"0123456789",""),"")).and.cod_sec<>"*"
if wnum=0
   return
endif
seek worden_i
copy to &wtmq fields serial,dirdes1,dir_ori delimited while orden<=worden_f ;
   for empty(chrtran(dir_num,chrtran(dir_num,"0123456789",""),"")).and.cod_sec<>"*"
*** se renombra al final para que el servidor web no lea el archivo a medias
rename &wtmq to &wreq
?"...Ajustando direcciones (ERP):",tran(wnum,"9,999"),"guias sin dir_num"
wini=seconds()
do while .not.file(wok).and.seconds()-wini<120
   =inkey(2)
enddo
if .not.file(wok)
   if file(wreq)
      erase &wreq
   endif
   do aviso with "Servidor web no respondio: sigue SIN ajuste de direcciones"
   return
endif
*** tabla temporal con los mismos anchos de serial, dirdes1 y dir_num
copy stru to /u/tmp/dn_resp fields serial,dirdes1,dir_num
sele 0
use /u/tmp/dn_resp excl alias dnr
appe from &wok delimited
waju=reccount()
inde on serial to /u/tmp/dn_resp
sele 1
set rela to serial into dnr
seek worden_i
repl dir_num with dnr.dir_num, dirdes1 with dnr.dirdes1 while orden<=worden_f ;
   for .not.eof("dnr").and.empty(chrtran(dir_num,chrtran(dir_num,"0123456789",""),"")).and.cod_sec<>"*"
set rela to
sele dnr
use
erase &wok
erase /u/tmp/dn_resp.dbf
erase /u/tmp/dn_resp.idx
sele 1
?"  Direcciones ajustadas (ERP):",tran(waju,"9,999")
return
