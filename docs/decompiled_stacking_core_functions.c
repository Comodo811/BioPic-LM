/*
 Extracted decompiled stacking core functions from decomp.txt.
 This is not original source code; it is Ghidra-style decompiler output.
 Keep this file as a fast local reference while translating behavior into BioPic.
*/

/* ==================================================
 * Function: FUN_008c4c90
 * Address:  008c4c90
 * Namespace: Global
 * ================================================== */

void FUN_008c4c90(longlong param_1)

{
  char cVar1;
  int iVar2;
  undefined4 uVar3;
  longlong *plVar4;
  longlong lVar5;
  undefined8 local_e8;
  undefined8 local_e0;
  undefined8 local_d8;
  undefined8 local_d0;
  undefined8 local_c8;
  undefined8 local_c0;
  undefined8 local_b8;
  undefined8 local_b0;
  undefined8 local_a8;
  undefined8 local_a0;
  undefined8 local_98;
  undefined8 local_90;
  undefined8 local_88;
  undefined8 local_80;
  undefined8 local_78;
  undefined8 local_70;
  undefined8 local_68;
  undefined8 local_60;
  undefined8 local_58;
  undefined8 local_50;
  undefined8 local_48;
  undefined8 local_40;
  undefined8 local_38;
  longlong local_30;
  undefined8 local_28;
  undefined8 local_20 [2];
  
  local_e8 = 0;
  local_e0 = 0;
  local_d8 = 0;
  local_d0 = 0;
  local_c8 = 0;
  local_c0 = 0;
  local_b8 = 0;
  local_b0 = 0;
  local_a8 = 0;
  local_a0 = 0;
  local_98 = 0;
  local_90 = 0;
  local_88 = 0;
  local_80 = 0;
  local_78 = 0;
  local_70 = 0;
  local_68 = 0;
  local_60 = 0;
  local_58 = 0;
  local_50 = 0;
  local_48 = 0;
  local_40 = 0;
  local_20[0] = 0;
  local_28 = 0;
  if (DAT_00968fb7 != '\0') goto LAB_008c5b4e;
  FUN_00412950(&local_28);
  if (*(char *)(*(longlong *)(*(longlong *)(param_1 + 0x90) + 0xb70) + 0x80) == '\0') {
    if (*(char *)(*(longlong *)(*(longlong *)(param_1 + 0x90) + 0xb68) + 0x80) == '\0') {
      if (*(char *)(*(longlong *)(*(longlong *)(param_1 + 0x90) + 0xb60) + 0x80) == '\0') {
        if (*(char *)(*(longlong *)(*(longlong *)(param_1 + 0x90) + 0xb48) + 0x80) == '\0') {
          if (*(char *)(*(longlong *)(*(longlong *)(param_1 + 0x90) + 0xb58) + 0x80) == '\0') {
            DAT_00969013 = '\0';
          }
          else {
            DAT_00969013 = '\x01';
          }
        }
        else {
          DAT_00969013 = '\x02';
        }
      }
      else {
        DAT_00969013 = '\x03';
      }
    }
    else {
      DAT_00969013 = '\x04';
    }
  }
  else {
    DAT_00969013 = '\x05';
  }
  plVar4 = *(longlong **)(*(longlong *)(param_1 + 0x90) + 0xa80);
  (**(code **)(*plVar4 + 0x2e0))(plVar4,DAT_00968fb3);
  if (DAT_00968e7d == '\0') {
    plVar4 = *(longlong **)(*(longlong *)(param_1 + 0x90) + 0xaf0);
    cVar1 = (**(code **)(*plVar4 + 0x2d8))(plVar4);
    if (cVar1 != '\0') {
      plVar4 = *(longlong **)(*(longlong *)(param_1 + 0x90) + 0xae8);
      cVar1 = (**(code **)(*plVar4 + 0x2d8))(plVar4);
      if (cVar1 != '\0') {
        FUN_008cca70(*(undefined8 *)(param_1 + 0x90),DAT_00968e60);
      }
    }
  }
  if (DAT_00968fb4 != '\0') {
    FUN_00413070(local_20,*(undefined8 *)PTR_DAT_00953ce8);
  }
  FUN_00412fe0(&DAT_00969018,L"Stacking");
  DAT_00969014 = DAT_00968e88;
  FUN_00899ac0(*(undefined8 *)PTR_DAT_00952260,DAT_00968e60);
  DAT_00968e76 = 1;
  FUN_006a7170(*(undefined8 *)(*(longlong *)(param_1 + 0x90) + 0x7e0),0);
  FUN_0073fbc0(*(undefined8 *)PTR_DAT_00953f68,0xfff5);
  if (DAT_00968e7d == '\0') {
    FUN_008c08c0(*(undefined8 *)(param_1 + 0x90));
  }
  FUN_005f07e0(*(undefined8 *)PTR_DAT_00952838,L"PROGRAM: Stacking in progress...");
  if (DAT_00968e7d == '\0') {
    FUN_008c2820(param_1);
  }
  FUN_008c1050(param_1);
  if (DAT_00968e7e == '\0') {
    FUN_008c1740(param_1);
  }
  DAT_00968e7e = '\x01';
  FUN_005f0770(*(undefined8 *)(DAT_00968e60 + 0x808),&local_40);
  iVar2 = FUN_00414320(local_40,&DAT_008c5c8c);
  if (0 < iVar2) {
    FUN_008c4770(param_1);
  }
  FUN_005f0770(*(undefined8 *)(*(longlong *)(param_1 + 0x90) + 0xa48),&local_48);
  iVar2 = FUN_004143b0(local_48,&DAT_008c5c8c);
  if (iVar2 != 0) {
    FUN_005f0770(*(undefined8 *)(*(longlong *)(param_1 + 0x90) + 0x808),&local_50);
    iVar2 = FUN_00414320(local_50,&DAT_008c5c9c);
    if (0 < iVar2) {
      FUN_008c3240(param_1);
    }
  }
  FUN_008c4290(param_1);
  (**(code **)(*DAT_00968ef8 + 0x10))(DAT_00968ef8,DAT_00968f98);
  FUN_008bc260(*(undefined8 *)(param_1 + 0x90),DAT_00968ef8);
  local_30 = *(longlong *)(*(longlong *)PTR_DAT_00953178 + 0x738);
  plVar4 = (longlong *)FUN_005ae7d0(*(undefined8 *)(local_30 + 0x338));
  (**(code **)(*plVar4 + 0x10))(plVar4,DAT_00968ef8);
  lVar5 = FUN_006a6780(local_30);
  FUN_005a8450(*(undefined8 *)(lVar5 + 0x80),1);
  lVar5 = FUN_006a6780(local_30);
  FUN_005a8250(*(undefined8 *)(lVar5 + 0x80),0xc0c0c0);
  lVar5 = FUN_006a6780(local_30);
  FUN_005a7510(*(undefined8 *)(lVar5 + 0x70),L"arial");
  lVar5 = FUN_006a6780(local_30);
  FUN_005a75c0(*(undefined8 *)(lVar5 + 0x70),0xe);
  plVar4 = (longlong *)FUN_006a6780(local_30);
  (**(code **)(*plVar4 + 0x120))(plVar4,5,5,L" Overlay: Stacked image + depth map ");
  DAT_00968e7d = '\x01';
  local_38 = *(undefined8 *)(*(longlong *)(*(longlong *)(param_1 + 0x90) + 0x860) + 0x78);
  iVar2 = FUN_00414610(L"Original",local_38,1);
  if (0 < iVar2) {
    iVar2 = FUN_004143b0(DAT_00968eb0,L"asis");
    if (iVar2 == 0) {
      FUN_00412fe0(&DAT_00968eb0,L".bmp");
    }
  }
  FUN_00413070(param_1 + 0x60,DAT_00968eb0);
  plVar4 = *(longlong **)(*(longlong *)(param_1 + 0x90) + 0xaf0);
  cVar1 = (**(code **)(*plVar4 + 0x2d8))(plVar4);
  if (cVar1 != '\0') {
    plVar4 = *(longlong **)(*(longlong *)(param_1 + 0x90) + 0xae0);
    cVar1 = (**(code **)(*plVar4 + 0x2d8))(plVar4);
    if (cVar1 == '\0') {
      FUN_004141b0(param_1 + 0x60,L"_al2",*(undefined8 *)(param_1 + 0x60));
    }
    else {
      FUN_004141b0(param_1 + 0x60,L"_al1",*(undefined8 *)(param_1 + 0x60));
    }
  }
  plVar4 = *(longlong **)(*(longlong *)(param_1 + 0x90) + 0xb38);
  cVar1 = (**(code **)(*plVar4 + 0x2d8))(plVar4);
  if (cVar1 != '\0') {
    FUN_004141b0(param_1 + 0x60,&DAT_008c5d9c,*(undefined8 *)(param_1 + 0x60));
  }
  if (DAT_00968e72 != '\0') {
    FUN_0043ad90(&local_58,DAT_00968e72);
    FUN_004142e0(param_1 + 0x60,3,L"_pam",local_58,*(undefined8 *)(param_1 + 0x60));
  }
  if (DAT_00969013 != '\x02') {
    if (DAT_00969013 == '\x05') {
      FUN_004141b0(param_1 + 0x60,L"_bgcol",*(undefined8 *)(param_1 + 0x60));
    }
    else if (DAT_00969013 == '\x04') {
      FUN_004141b0(param_1 + 0x60,L"_bglast",*(undefined8 *)(param_1 + 0x60));
    }
    else if (DAT_00969013 == '\x03') {
      FUN_004141b0(param_1 + 0x60,L"_bgmix",*(undefined8 *)(param_1 + 0x60));
    }
    else if (DAT_00969013 == '\x01') {
      FUN_004141b0(param_1 + 0x60,L"_bgbrit",*(undefined8 *)(param_1 + 0x60));
    }
    else if (DAT_00969013 == '\0') {
      FUN_004141b0(param_1 + 0x60,L"_bgdark",*(undefined8 *)(param_1 + 0x60));
    }
  }
  plVar4 = *(longlong **)(*(longlong *)(param_1 + 0x90) + 0xab0);
  cVar1 = (**(code **)(*plVar4 + 0x2d8))(plVar4);
  if (cVar1 == '\0') {
    FUN_005f0770(*(undefined8 *)(*(longlong *)(param_1 + 0x90) + 0xa08),&local_60);
    FUN_004142e0(param_1 + 0x60,3,L"_fil",local_60,*(undefined8 *)(param_1 + 0x60));
  }
  plVar4 = *(longlong **)(*(longlong *)(param_1 + 0x90) + 0xac0);
  cVar1 = (**(code **)(*plVar4 + 0x2d8))(plVar4);
  if (cVar1 == '\0') {
    plVar4 = *(longlong **)(*(longlong *)(param_1 + 0x90) + 0xab8);
    cVar1 = (**(code **)(*plVar4 + 0x2d8))(plVar4);
    if (cVar1 != '\0') goto LAB_008c553d;
  }
  else {
LAB_008c553d:
    plVar4 = *(longlong **)(*(longlong *)(param_1 + 0x90) + 0xac0);
    cVar1 = (**(code **)(*plVar4 + 0x2d8))(plVar4);
    if (cVar1 == '\0') {
      FUN_005f0770(*(undefined8 *)(*(longlong *)(param_1 + 0x90) + 0x920),&local_70);
      FUN_004142e0(param_1 + 0x60,3,&DAT_008c5e80,local_70,*(undefined8 *)(param_1 + 0x60));
    }
    else {
      FUN_005f0770(*(undefined8 *)(*(longlong *)(param_1 + 0x90) + 0x920),&local_68);
      FUN_004142e0(param_1 + 0x60,3,&DAT_008c5e6c,local_68,*(undefined8 *)(param_1 + 0x60));
    }
  }
  FUN_005f0770(*(undefined8 *)(*(longlong *)(param_1 + 0x90) + 0xa48),&local_78);
  iVar2 = FUN_004143b0(local_78,&DAT_008c5c8c);
  if (iVar2 != 0) {
    FUN_005f0770(*(undefined8 *)(*(longlong *)(param_1 + 0x90) + 0xa48),&local_80);
    FUN_004142e0(param_1 + 0x60,3,&DAT_008c5e94,local_80,*(undefined8 *)(param_1 + 0x60));
  }
  FUN_005f0770(*(undefined8 *)(*(longlong *)(param_1 + 0x90) + 0x808),&local_88);
  iVar2 = FUN_00414320(local_88,&DAT_008c5c8c);
  if (0 < iVar2) {
    FUN_005f0770(*(undefined8 *)(*(longlong *)(param_1 + 0x90) + 0x808),&local_90);
    FUN_004142e0(param_1 + 0x60,3,L"_sup",local_90,*(undefined8 *)(param_1 + 0x60));
  }
  if (DAT_00969010 != '\0') {
    FUN_0043ad90(&local_98,DAT_00969010);
    FUN_004142e0(param_1 + 0x60,3,L"_skip",local_98,*(undefined8 *)(param_1 + 0x60));
  }
  if (DAT_00968fb4 != '\0') {
    if (DAT_00968e68 < 10) {
      FUN_0043ad90(&local_a0,DAT_00968e68);
      FUN_004141b0(&local_28,&DAT_008c5c8c,local_a0);
    }
    else {
      FUN_0043ad90(&local_a8,DAT_00968e68);
      FUN_004141b0(&local_28,local_a8,DAT_00968ea0);
    }
  }
  FUN_0043ad90(&local_b0,*PTR_DAT_00952538);
  FUN_004142e0(&DAT_00968ec8,6,local_28,DAT_00968ea0,DAT_00968ea8,L"stk#",local_b0,
               *(undefined8 *)(param_1 + 0x60));
  if (DAT_00968e78 != '\0') {
    FUN_0085f440(&local_b8);
    FUN_004141b0(&DAT_00968ec8,local_b8,DAT_00968ec8);
  }
  plVar4 = *(longlong **)(*(longlong *)(param_1 + 0x90) + 0xb38);
  cVar1 = (**(code **)(*plVar4 + 0x2d8))(plVar4);
  if (cVar1 != '\0') {
    FUN_008603b0(DAT_00968f98,DAT_00968f98,0xf,1);
    FUN_008603b0(DAT_00968f98,DAT_00968f98,0xf,2);
    FUN_00860c10(DAT_00968f98,DAT_00968f98,2,0x19);
    FUN_0089caf0(*(undefined8 *)PTR_DAT_009526e8,DAT_00968f98,0x66);
    plVar4 = (longlong *)
             FUN_005ae7d0(*(undefined8 *)
                           (*(longlong *)(*(longlong *)PTR_DAT_00952838 + 0x738) + 0x338));
    (**(code **)(*plVar4 + 0x10))(plVar4,DAT_00968f98);
  }
  if (DAT_00968e82 != 0) {
    FUN_00412fe0(PTR_DAT_00953ce8,*(undefined8 *)PTR_DAT_00952830);
  }
  FUN_008bfdb0(*(undefined8 *)(param_1 + 0x90),DAT_00968f98,DAT_00968ec8);
  FUN_004141b0(&local_c0,L"[X] ",DAT_00968ec8);
  cVar1 = FUN_008bda70(*(undefined8 *)(param_1 + 0x90),local_c0);
  if (cVar1 != '\0') {
    FUN_004141b0(&local_c8,L"[_] ",DAT_00968ec8);
    cVar1 = FUN_008bda70(*(undefined8 *)(param_1 + 0x90),local_c8);
    if (cVar1 != '\0') {
      FUN_004141b0(&local_d0,L"[_] ",DAT_00968ec8);
      plVar4 = *(longlong **)(*(longlong *)(*(longlong *)(param_1 + 0x90) + 0x770) + 0x4e0);
      (**(code **)(*plVar4 + 200))(plVar4,0,local_d0);
    }
  }
  FUN_004141b0(&local_d8,L"PROGRAM: R e s u l t  ",DAT_00968ec8);
  FUN_005f07e0(*(undefined8 *)PTR_DAT_00952838,local_d8);
  if (DAT_00968e7f != '\0') {
    uVar3 = FUN_00414610(L"stk#",DAT_00968ec8,1);
    FUN_004144e0(L"map#",&DAT_00968ec8,uVar3);
    uVar3 = FUN_00414610(L"stk#",DAT_00968ec8,1);
    FUN_00414460(&DAT_00968ec8,uVar3,4);
    FUN_008bfdb0(*(undefined8 *)(param_1 + 0x90),DAT_00968f78,DAT_00968ec8);
    FUN_004141b0(&local_e0,L"[_] ",DAT_00968ec8);
    cVar1 = FUN_008bda70(*(undefined8 *)(param_1 + 0x90),local_e0);
    if (cVar1 != '\0') {
      FUN_004141b0(&local_e8,L"[_] ",DAT_00968ec8);
      plVar4 = *(longlong **)(*(longlong *)(*(longlong *)(param_1 + 0x90) + 0x770) + 0x4e0);
      (**(code **)(*plVar4 + 200))(plVar4,1,local_e8);
    }
  }
LAB_008c5b4e:
  FUN_00412a30(&local_e8,0xb);
  FUN_00412a30(&local_90,7);
  FUN_00412950(&local_58);
  FUN_00412a30(&local_50,3);
  FUN_00412a30(&local_28,2);
  return;
}

/* ==================================================
 * Function: FUN_008c2820
 * Address:  008c2820
 * Namespace: Global
 * ================================================== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

void FUN_008c2820(longlong param_1)

{
  char cVar1;
  undefined8 uVar2;
  longlong *plVar3;
  double dVar4;
  undefined1 auStack_128 [32];
  short local_108;
  char local_100;
  undefined8 local_f0;
  undefined8 local_e8;
  longlong local_e0;
  undefined8 local_d8;
  undefined8 local_d0;
  longlong *local_c8;
  longlong *local_c0;
  longlong *local_b8;
  longlong *local_b0;
  longlong *local_a8;
  longlong *local_a0;
  longlong *local_98;
  longlong *local_90;
  longlong *local_88;
  longlong *local_80;
  longlong *local_78;
  undefined8 local_70;
  undefined8 local_68;
  char local_59;
  longlong *local_58;
  longlong *local_50;
  double local_48;
  double local_40;
  short local_34;
  short local_32;
  undefined8 local_30;
  ushort local_22;
  longlong *local_20;
  
  local_e8 = 0;
  local_f0 = 0;
  local_e0 = 0;
  local_d8 = 0;
  local_d0 = 0;
  local_30 = 0;
  plVar3 = *(longlong **)(*(longlong *)(param_1 + 0x90) + 0xaf0);
  local_59 = (**(code **)(*plVar3 + 0x2d8))(plVar3);
  local_40 = DAT_008c31e0 / (double)DAT_00968e88;
  plVar3 = *(longlong **)(*(longlong *)(param_1 + 0x90) + 0xab8);
  cVar1 = (**(code **)(*plVar3 + 0x2d8))(plVar3);
  if (cVar1 == '\0') {
    plVar3 = *(longlong **)(*(longlong *)(param_1 + 0x90) + 0xac0);
    cVar1 = (**(code **)(*plVar3 + 0x2d8))(plVar3);
    if (cVar1 == '\0') {
      *(undefined8 *)(param_1 + 0x68) = 0xbf9eb851eb851eb8;
      goto LAB_008c29ed;
    }
  }
  plVar3 = *(longlong **)(*(longlong *)(param_1 + 0x90) + 0xac0);
  cVar1 = (**(code **)(*plVar3 + 0x2d8))(plVar3);
  if (cVar1 == '\0') {
    FUN_005f0770(*(undefined8 *)(*(longlong *)(param_1 + 0x90) + 0x920),&local_d8);
    local_70 = local_d8;
    dVar4 = (double)FUN_00440120(local_d8,PTR_DAT_009537e8);
    *(double *)(param_1 + 0x68) = dVar4 * _DAT_008c31f0 + DAT_008c31e8;
  }
  else {
    FUN_005f0770(*(undefined8 *)(*(longlong *)(param_1 + 0x90) + 0x920),&local_d0);
    local_68 = local_d0;
    dVar4 = (double)FUN_00440120(local_d0,PTR_DAT_009537e8);
    *(double *)(param_1 + 0x68) = DAT_008c31e8 - dVar4 * _DAT_008c31f0;
  }
LAB_008c29ed:
  local_20 = (longlong *)FUN_005b31e0(PTR_PTR_005a1410,1);
  local_50 = (longlong *)FUN_005b31e0(PTR_PTR_005a1410);
  local_32 = 0;
  DAT_00968e86 = DAT_00968e88;
  DAT_00969011 = '\0';
  plVar3 = *(longlong **)(*(longlong *)(*(longlong *)(param_1 + 0x90) + 0x770) + 0x4e0);
  local_34 = (**(code **)(*plVar3 + 0x28))(plVar3);
  local_34 = local_34 + -1;
  if (DAT_00968e88 < 0x100) {
    DAT_00969012 = '\x01';
  }
  else {
    DAT_00969012 = (char)((ulonglong)DAT_00968e88 / 0xff) + '\x01';
  }
  do {
    if ((DAT_00968e86 == 0) || (DAT_00968fb7 != '\0')) {
      if (DAT_00968e7e == '\0') {
        FUN_0085fcc0(DAT_00968f50,local_32,DAT_00969012);
      }
      plVar3 = local_20;
      local_b8 = local_20;
      local_20 = (longlong *)0x0;
      FUN_0040f6e0(plVar3);
      plVar3 = local_50;
      local_c0 = local_50;
      local_50 = (longlong *)0x0;
      FUN_0040f6e0(plVar3);
      plVar3 = local_58;
      if (local_59 != '\0') {
        local_c8 = local_58;
        local_58 = (longlong *)0x0;
        FUN_0040f6e0(plVar3);
      }
      FUN_00412a30(&local_f0,3);
      FUN_00412a30(&local_d8,2);
      FUN_00412950(&local_30);
      return;
    }
    local_22 = FUN_0040c470((double)DAT_00968e86 * local_40);
    local_48 = DAT_008c31f8 -
               (*(double *)(param_1 + 0x68) * (double)(int)(local_22 - 0x7f)) / DAT_008c31e0;
    for (; local_34 != 0; local_34 = local_34 + -1) {
      plVar3 = *(longlong **)(*(longlong *)(*(longlong *)(param_1 + 0x90) + 0x770) + 0x4e0);
      (**(code **)(*plVar3 + 0x18))(plVar3,&local_e0,local_34);
      if (*(short *)(local_e0 + 2) == 0x58) break;
    }
    plVar3 = DAT_00968f70;
    if (DAT_00969011 == '\0') {
      local_78 = DAT_00968f70;
      DAT_00968f70 = (longlong *)0x0;
      FUN_0040f6e0(plVar3);
      DAT_00968f70 = (longlong *)FUN_005b31e0(PTR_PTR_005a1410,1);
      plVar3 = local_50;
      local_80 = local_50;
      local_50 = (longlong *)0x0;
      FUN_0040f6e0(plVar3);
      local_50 = (longlong *)FUN_005b31e0(PTR_PTR_005a1410,1);
      plVar3 = *(longlong **)(*(longlong *)(*(longlong *)(param_1 + 0x90) + 0x770) + 0x4e0);
      (**(code **)(*plVar3 + 0x18))(plVar3,&local_f0,local_34);
      FUN_00414400(&local_e8,local_f0,5,0xf9);
      FUN_008bde10(*(undefined8 *)(param_1 + 0x90),local_e8,DAT_00968f70);
      if ((byte)*PTR_DAT_00952538 < 3) {
        *PTR_DAT_00953600 = 1;
      }
      else {
        *PTR_DAT_00953600 = 2;
      }
      if (*PTR_DAT_00953600 == '\x01') {
        (**(code **)(*local_50 + 0x10))(local_50,DAT_00968f70);
      }
      else {
        FUN_00863980(DAT_00968f70,local_50);
      }
      if (DAT_00968e86 == DAT_00968e88) {
        DAT_00968ff8 = (**(code **)(*DAT_00968f70 + 0x60))(DAT_00968f70);
        DAT_00968ffa = (**(code **)(*DAT_00968f70 + 0x48))(DAT_00968f70);
        plVar3 = DAT_00968f80;
        local_88 = DAT_00968f80;
        DAT_00968f80 = (longlong *)0x0;
        FUN_0040f6e0(plVar3);
        DAT_00968f80 = (longlong *)FUN_005b31e0(PTR_PTR_005a1410,1);
        plVar3 = DAT_00968f88;
        local_90 = DAT_00968f88;
        DAT_00968f88 = (longlong *)0x0;
        FUN_0040f6e0(plVar3);
        DAT_00968f88 = (longlong *)FUN_005b31e0(PTR_PTR_005a1410,1);
        plVar3 = DAT_00968f90;
        local_98 = DAT_00968f90;
        DAT_00968f90 = (longlong *)0x0;
        FUN_0040f6e0(plVar3);
        DAT_00968f90 = (longlong *)FUN_005b31e0(PTR_PTR_005a1410,1);
        plVar3 = DAT_00968f38;
        local_a0 = DAT_00968f38;
        DAT_00968f38 = (longlong *)0x0;
        FUN_0040f6e0(plVar3);
        DAT_00968f38 = (longlong *)FUN_005b31e0(PTR_PTR_005a1410,1);
        plVar3 = DAT_00968f40;
        local_a8 = DAT_00968f40;
        DAT_00968f40 = (longlong *)0x0;
        FUN_0040f6e0(plVar3);
        DAT_00968f40 = (longlong *)FUN_005b31e0(PTR_PTR_005a1410,1);
        plVar3 = DAT_00968f48;
        local_b0 = DAT_00968f48;
        DAT_00968f48 = (longlong *)0x0;
        FUN_0040f6e0(plVar3);
        DAT_00968f48 = (longlong *)FUN_005b31e0(PTR_PTR_005a1410,1);
        (**(code **)(*DAT_00968f80 + 0x10))(DAT_00968f80,DAT_00968f70);
        (**(code **)(*DAT_00968f88 + 0x10))(DAT_00968f88,DAT_00968f80);
        (**(code **)(*DAT_00968f90 + 0x10))(DAT_00968f90,DAT_00968f80);
        (**(code **)(*DAT_00968f38 + 0x10))(DAT_00968f38,DAT_00968f70);
        FUN_008638e0(DAT_00968f38,0);
        (**(code **)(*DAT_00968f40 + 0x10))(DAT_00968f40,DAT_00968f38);
        (**(code **)(*DAT_00968f48 + 0x10))(DAT_00968f48,DAT_00968f38);
        (**(code **)(*DAT_00968ee8 + 0x10))(DAT_00968ee8,DAT_00968f70);
        if (local_59 != '\0') {
          local_58 = (longlong *)FUN_005b31e0(PTR_PTR_005a1410,1);
          (**(code **)(*local_58 + 0x10))(local_58,DAT_00968f70);
          FUN_008c0fc0();
        }
      }
      else {
        FUN_008c2750(auStack_128);
        if (local_59 != '\0') {
          uVar2 = FUN_00865340(local_58,DAT_00968f70,0);
          (**(code **)(*DAT_00968f70 + 0x10))(DAT_00968f70,uVar2);
          (**(code **)(*local_58 + 0x10))(local_58,DAT_00968f70);
          if ((byte)*PTR_DAT_00953600 < 2) {
            (**(code **)(*local_50 + 0x10))(local_50,local_58);
          }
          else {
            FUN_00863980(DAT_00968f70,local_50);
          }
        }
      }
      if (DAT_00968e7e == '\0') {
        local_108 = local_32;
        local_100 = DAT_00969012;
        FUN_0085ffb0(local_50,DAT_00968f60,DAT_00968f68,DAT_00968f50);
        local_32 = local_32 + 1;
      }
      (**(code **)(*local_20 + 0x10))(local_20,local_50);
      FUN_0085f120(local_50,local_20,local_48);
      FUN_008c1ac0(auStack_128);
      if (DAT_00968e77 != '\0') {
        FUN_008c24b0(auStack_128);
      }
      if (DAT_00968e72 < 0x32) {
        plVar3 = (longlong *)
                 FUN_005ae7d0(*(undefined8 *)
                               (*(longlong *)(*(longlong *)PTR_DAT_00952838 + 0x738) + 0x338));
        (**(code **)(*plVar3 + 0x10))(plVar3,DAT_00968f88);
      }
      else {
        plVar3 = (longlong *)
                 FUN_005ae7d0(*(undefined8 *)
                               (*(longlong *)(*(longlong *)PTR_DAT_00952838 + 0x738) + 0x338));
        (**(code **)(*plVar3 + 0x10))(plVar3,DAT_00968ee8);
      }
      DAT_00969011 = DAT_00969010;
    }
    else {
      DAT_00969011 = DAT_00969011 + -1;
    }
    FUN_00743f80(*(undefined8 *)PTR_DAT_009533c0);
    DAT_00968e86 = DAT_00968e86 - 1;
    local_34 = local_34 + -1;
  } while( true );
}

/* ==================================================
 * Function: FUN_008c1ac0
 * Address:  008c1ac0
 * Namespace: Global
 * ================================================== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

void FUN_008c1ac0(longlong param_1)

{
  ulonglong uVar1;
  short sVar2;
  int iVar3;
  ulonglong uVar4;
  ushort uVar5;
  short sVar6;
  undefined8 local_90 [2];
  byte local_7f;
  ushort local_7e;
  ushort local_7c;
  ushort local_7a;
  longlong local_78;
  longlong local_70;
  longlong local_68;
  longlong local_60;
  longlong local_58;
  longlong local_50;
  longlong local_48;
  longlong local_40;
  longlong local_38;
  longlong local_30;
  ushort local_28;
  ushort local_26;
  ushort local_24;
  ushort local_22;
  ushort local_20;
  ushort local_1e;
  ushort local_1c;
  ushort local_1a;
  
  local_90[0] = 0;
  FUN_005f0770(*(undefined8 *)(*(longlong *)(*(longlong *)(param_1 + 0x130) + 0x90) + 0x808),
               local_90);
  sVar2 = FUN_0043b040(local_90[0]);
  local_1a = sVar2 * 3;
  iVar3 = (**(code **)(**(longlong **)(param_1 + 0x108) + 0x60))(*(longlong **)(param_1 + 0x108));
  local_7f = (byte)((longlong)(ulonglong)(DAT_00968ff8 + 3) / (longlong)iVar3);
  local_24 = (ushort)local_7f * 3;
  uVar5 = DAT_00968ffa + (ushort)local_7f * -3;
  if (local_24 <= uVar5) {
    sVar2 = uVar5 + (ushort)local_7f * -3 + 1;
    do {
      local_48 = FUN_005b4690(DAT_00968f70,local_24);
      local_50 = FUN_005b4690(DAT_00968f80,local_24);
      local_58 = FUN_005b4690(DAT_00968f88,local_24);
      local_60 = FUN_005b4690(DAT_00968f90,local_24);
      local_68 = FUN_005b4690(DAT_00968f38,local_24);
      local_70 = FUN_005b4690(DAT_00968f40,local_24);
      local_78 = FUN_005b4690(DAT_00968f48,local_24);
      local_38 = FUN_005b4690(DAT_00968ee8,local_24);
      local_40 = FUN_005b4690(DAT_00968ef0);
      local_30 = FUN_005b4690(*(undefined8 *)(param_1 + 0x108));
      local_22 = (ushort)local_7f * 3;
      uVar5 = DAT_00968ff8 + (ushort)local_7f * -4;
      if (local_22 <= uVar5) {
        sVar6 = uVar5 + (ushort)local_7f * -3 + 1;
        do {
          local_26 = local_22 * 3;
          local_28 = (local_22 / local_7f) * 3;
          local_1c = (ushort)*(byte *)(local_30 + (ulonglong)local_28);
          if ((ushort)(*(byte *)(local_68 + (ulonglong)local_26) + 1) < local_1c) {
            local_7c = FUN_0040c470((double)((uint)*(byte *)(local_68 + (ulonglong)local_26) * 0x33)
                                    / (double)local_1c);
            local_7e = 0xff - local_7c;
            *(char *)(local_50 + (ulonglong)local_26) =
                 (char)((ulonglong)
                        ((uint)*(byte *)(local_50 + (ulonglong)local_26) * (uint)local_7c +
                         (uint)*(byte *)(local_48 + (ulonglong)local_26) * (uint)local_7e + 0x7f) /
                       0xff);
            *(char *)(local_50 + (ulonglong)(local_26 + 1)) =
                 (char)((ulonglong)
                        ((uint)*(byte *)(local_50 + (ulonglong)(local_26 + 1)) * (uint)local_7c +
                         (uint)*(byte *)(local_48 + (ulonglong)(local_26 + 1)) * (uint)local_7e +
                        0x7f) / 0xff);
            *(char *)(local_50 + (ulonglong)(local_26 + 2)) =
                 (char)((ulonglong)
                        ((uint)*(byte *)(local_50 + (ulonglong)(local_26 + 2)) * (uint)local_7c +
                         (uint)*(byte *)(local_48 + (ulonglong)(local_26 + 2)) * (uint)local_7e +
                        0x7f) / 0xff);
            *(char *)(local_68 + (ulonglong)local_26) =
                 (char)((ulonglong)
                        ((uint)*(byte *)(local_68 + (ulonglong)local_26) * (uint)local_7c +
                         (uint)local_1c * (uint)local_7e + 0x7f) / 0xff);
            *(char *)(local_68 + (ulonglong)(local_26 + 2)) =
                 (char)((ulonglong)
                        ((uint)*(byte *)(local_68 + (ulonglong)(local_26 + 2)) * (uint)local_7c +
                         (uint)*(ushort *)(param_1 + 0x106) * (uint)local_7e + 0x7f) / 0xff);
          }
          local_28 = local_28 + 1;
          local_1e = (ushort)*(byte *)(local_30 + (ulonglong)local_28);
          if ((ushort)(*(byte *)(local_70 + (ulonglong)local_26) + 1) < local_1e) {
            local_7c = FUN_0040c470((double)((ulonglong)*(byte *)(local_70 + (ulonglong)local_26) <<
                                            6) / (double)local_1e);
            local_7e = 0xff - local_7c;
            *(char *)(local_58 + (ulonglong)local_26) =
                 (char)((ulonglong)
                        ((uint)*(byte *)(local_58 + (ulonglong)local_26) * (uint)local_7c +
                         (uint)*(byte *)(local_48 + (ulonglong)local_26) * (uint)local_7e + 0x7f) /
                       0xff);
            *(char *)(local_58 + (ulonglong)(local_26 + 1)) =
                 (char)((ulonglong)
                        ((uint)*(byte *)(local_58 + (ulonglong)(local_26 + 1)) * (uint)local_7c +
                         (uint)*(byte *)(local_48 + (ulonglong)(local_26 + 1)) * (uint)local_7e +
                        0x7f) / 0xff);
            *(char *)(local_58 + (ulonglong)(local_26 + 2)) =
                 (char)((ulonglong)
                        ((uint)*(byte *)(local_58 + (ulonglong)(local_26 + 2)) * (uint)local_7c +
                         (uint)*(byte *)(local_48 + (ulonglong)(local_26 + 2)) * (uint)local_7e +
                        0x7f) / 0xff);
            *(char *)(local_70 + (ulonglong)local_26) =
                 (char)((ulonglong)
                        ((uint)*(byte *)(local_70 + (ulonglong)local_26) * (uint)local_7c +
                         (uint)local_1e * (uint)local_7e + 0x7f) / 0xff);
            *(char *)(local_70 + (ulonglong)(local_26 + 2)) =
                 (char)((ulonglong)
                        ((uint)*(byte *)(local_70 + (ulonglong)(local_26 + 2)) * (uint)local_7c +
                         (uint)*(ushort *)(param_1 + 0x106) * (uint)local_7e + 0x7f) / 0xff);
          }
          local_28 = local_28 + 1;
          local_20 = (ushort)*(byte *)(local_30 + (ulonglong)local_28);
          uVar4 = (ulonglong)local_26;
          if ((ushort)(*(byte *)(local_78 + uVar4) + 1) < local_20) {
            local_7c = FUN_0040c470((double)((uint)*(byte *)(local_78 + (ulonglong)local_26) * 0x55)
                                    / (double)local_20);
            local_7e = 0xff - local_7c;
            *(char *)(local_60 + (ulonglong)local_26) =
                 (char)((ulonglong)
                        ((uint)*(byte *)(local_60 + (ulonglong)local_26) * (uint)local_7c +
                         (uint)*(byte *)(local_48 + (ulonglong)local_26) * (uint)local_7e + 0x7f) /
                       0xff);
            *(char *)(local_60 + (ulonglong)(local_26 + 1)) =
                 (char)((ulonglong)
                        ((uint)*(byte *)(local_60 + (ulonglong)(local_26 + 1)) * (uint)local_7c +
                         (uint)*(byte *)(local_48 + (ulonglong)(local_26 + 1)) * (uint)local_7e +
                        0x7f) / 0xff);
            *(char *)(local_60 + (ulonglong)(local_26 + 2)) =
                 (char)((ulonglong)
                        ((uint)*(byte *)(local_60 + (ulonglong)(local_26 + 2)) * (uint)local_7c +
                         (uint)*(byte *)(local_48 + (ulonglong)(local_26 + 2)) * (uint)local_7e +
                        0x7f) / 0xff);
            *(char *)(local_78 + (ulonglong)local_26) =
                 (char)((ulonglong)
                        ((uint)*(byte *)(local_78 + (ulonglong)local_26) * (uint)local_7c +
                         (uint)local_20 * (uint)local_7e + 0x7f) / 0xff);
            uVar1 = (ulonglong)
                    ((uint)*(byte *)(local_78 + (ulonglong)(local_26 + 2)) * (uint)local_7c +
                     (uint)*(ushort *)(param_1 + 0x106) * (uint)local_7e + 0x7f);
            uVar4 = uVar1 % 0xff;
            *(char *)(local_78 + (ulonglong)(local_26 + 2)) = (char)(uVar1 / 0xff);
          }
          local_7a = FUN_0040c470((double)((uint)local_1c * 2 + (uint)local_1e) / _DAT_008c2480,
                                  uVar4);
          if ((local_1a < local_7a) && (*(byte *)(local_40 + (ulonglong)local_26) <= local_7a)) {
            FUN_00409900(local_48 + (ulonglong)local_26,local_38 + (ulonglong)local_26,3);
            *(undefined1 *)(local_40 + (ulonglong)(local_26 + 2)) = *(undefined1 *)(param_1 + 0x106)
            ;
          }
          *(undefined1 *)(local_40 + (ulonglong)local_26) = (undefined1)local_7a;
          local_22 = local_22 + 1;
          sVar6 = sVar6 + -1;
        } while (sVar6 != 0);
      }
      local_24 = local_24 + 1;
      sVar2 = sVar2 + -1;
    } while (sVar2 != 0);
  }
  FUN_00412950(local_90);
  return;
}

/* ==================================================
 * Function: FUN_008c1050
 * Address:  008c1050
 * Namespace: Global
 * ================================================== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

void FUN_008c1050(longlong param_1)

{
  longlong *plVar1;
  undefined1 uVar2;
  short sVar3;
  short sVar4;
  undefined8 local_80 [2];
  byte local_6a;
  char local_69;
  longlong local_68;
  longlong local_60;
  longlong local_58;
  longlong local_50;
  longlong local_48;
  longlong local_40;
  longlong local_38;
  longlong local_30;
  uint local_28;
  ushort local_24;
  ushort local_22;
  ushort local_20;
  short local_1e;
  short local_1c;
  ushort local_1a;
  
  local_80[0] = 0;
  (**(code **)(*DAT_00968f98 + 0x10))(DAT_00968f98,DAT_00968f88);
  (**(code **)(*DAT_00968fa0 + 0x10))(DAT_00968fa0,DAT_00968f88);
  plVar1 = *(longlong **)(*(longlong *)(param_1 + 0x90) + 0xab0);
  local_69 = (**(code **)(*plVar1 + 0x2d8))(plVar1);
  FUN_005f0770(*(undefined8 *)(*(longlong *)(param_1 + 0x90) + 0xa08),local_80);
  local_6a = FUN_0043b040(local_80[0]);
  if (local_69 == '\0') {
    if (local_6a == 1) {
      local_20 = 0xff;
      local_22 = 0;
      local_24 = 0;
    }
    else if ((byte)(local_6a - 2) < 4) {
      local_20 = (ushort)local_6a * -0x40 + 0x140;
      local_22 = 0xff - local_20;
      local_24 = 0;
    }
    else if ((byte)(local_6a - 6) < 4) {
      local_20 = (local_6a - 5) * -0x1e + 0x78;
      local_24 = (local_6a - 5) * 0x32;
      local_22 = 0xff - (local_20 + local_24);
    }
    else if (local_6a == 10) {
      local_20 = 0;
      local_22 = 0;
      local_24 = 0xff;
    }
  }
  sVar3 = (**(code **)(*DAT_00968f80 + 0x48))();
  local_1e = 0;
  do {
    local_30 = FUN_005b4690(DAT_00968f80,local_1e);
    local_38 = FUN_005b4690(DAT_00968f88,local_1e);
    local_40 = FUN_005b4690(DAT_00968f90,local_1e);
    local_48 = FUN_005b4690(DAT_00968f38,local_1e);
    local_50 = FUN_005b4690(DAT_00968f40,local_1e);
    local_58 = FUN_005b4690(DAT_00968f48,local_1e);
    local_60 = FUN_005b4690(DAT_00968f98,local_1e);
    local_68 = FUN_005b4690(DAT_00968fa0,local_1e);
    sVar4 = (**(code **)(*DAT_00968f80 + 0x60))();
    local_1c = 0;
    do {
      local_1a = local_1c * 3;
      if (local_69 != '\0') {
        local_28 = FUN_0040c470((double)*(byte *)(local_48 + (ulonglong)local_1a) * _DAT_008c16f0 +
                                _DAT_008c16f8 +
                                (double)*(byte *)(local_50 + (ulonglong)local_1a) * _DAT_008c1700 +
                                (double)*(byte *)(local_58 + (ulonglong)local_1a));
        local_20 = FUN_0040c470(((double)*(byte *)(local_48 + (ulonglong)local_1a) * _DAT_008c1708)
                                / (double)local_28);
        local_22 = FUN_0040c470(((double)*(byte *)(local_50 + (ulonglong)local_1a) * _DAT_008c1710)
                                / (double)local_28);
        local_24 = 0xff - (local_20 + local_22);
      }
      uVar2 = FUN_0040c470((double)((uint)*(byte *)(local_30 + (ulonglong)local_1a) * (uint)local_20
                                    + (uint)*(byte *)(local_38 + (ulonglong)local_1a) *
                                      (uint)local_22 +
                                    (uint)*(byte *)(local_40 + (ulonglong)local_1a) * (uint)local_24
                                   + 0x7f) / _DAT_008c1718);
      *(undefined1 *)(local_60 + (ulonglong)local_1a) = uVar2;
      uVar2 = FUN_0040c470((double)((uint)*(byte *)(local_30 + (ulonglong)(local_1a + 1)) *
                                    (uint)local_20 +
                                    (uint)*(byte *)(local_38 + (ulonglong)(local_1a + 1)) *
                                    (uint)local_22 +
                                    (uint)*(byte *)(local_40 + (ulonglong)(local_1a + 1)) *
                                    (uint)local_24 + 0x7f) / _DAT_008c1718);
      *(undefined1 *)(local_60 + (ulonglong)(local_1a + 1)) = uVar2;
      uVar2 = FUN_0040c470((double)((uint)*(byte *)(local_30 + (ulonglong)(local_1a + 2)) *
                                    (uint)local_20 +
                                    (uint)*(byte *)(local_38 + (ulonglong)(local_1a + 2)) *
                                    (uint)local_22 +
                                    (uint)*(byte *)(local_40 + (ulonglong)(local_1a + 2)) *
                                    (uint)local_24 + 0x7f) / _DAT_008c1718);
      *(undefined1 *)(local_60 + (ulonglong)(local_1a + 2)) = uVar2;
      uVar2 = FUN_0040c470((double)((uint)*(byte *)(local_48 + (ulonglong)local_1a) * (uint)local_20
                                    + (uint)*(byte *)(local_50 + (ulonglong)local_1a) *
                                      (uint)local_22 +
                                    (uint)*(byte *)(local_58 + (ulonglong)local_1a) * (uint)local_24
                                   + 0x7f) / _DAT_008c1718);
      *(undefined1 *)(local_68 + (ulonglong)local_1a) = uVar2;
      uVar2 = FUN_0040c470((double)((uint)*(byte *)(local_48 + (ulonglong)(local_1a + 2)) *
                                    (uint)local_20 +
                                    (uint)*(byte *)(local_50 + (ulonglong)(local_1a + 2)) *
                                    (uint)local_22 +
                                    (uint)*(byte *)(local_58 + (ulonglong)(local_1a + 2)) *
                                    (uint)local_24 + 0x7f) / _DAT_008c1718);
      *(undefined1 *)(local_68 + (ulonglong)(local_1a + 2)) = uVar2;
      local_1c = local_1c + 1;
      sVar4 = sVar4 + -1;
    } while (sVar4 != 0);
    local_1e = local_1e + 1;
    sVar3 = sVar3 + -1;
  } while (sVar3 != 0);
  FUN_00412950(local_80);
  return;
}

/* ==================================================
 * Function: FUN_008c1740
 * Address:  008c1740
 * Namespace: Global
 * ================================================== */

void FUN_008c1740(longlong param_1)

{
  longlong *plVar1;
  short sVar2;
  short sVar3;
  int iVar4;
  undefined8 local_50;
  undefined8 local_48;
  longlong local_40 [2];
  short local_2e;
  ushort local_2c;
  short local_2a;
  longlong local_28;
  longlong local_20;
  
  local_48 = 0;
  local_50 = 0;
  local_40[0] = 0;
  if (DAT_00969013 == '\x05') {
    FUN_008638e0(DAT_00968f58,
                 *(undefined4 *)(*(longlong *)(*(longlong *)(param_1 + 0x90) + 0x8e0) + 200));
  }
  else if (DAT_00969013 == '\x04') {
    plVar1 = *(longlong **)(*(longlong *)(*(longlong *)(param_1 + 0x90) + 0x770) + 0x4e0);
    local_2a = (**(code **)(*plVar1 + 0x28))(plVar1);
    do {
      local_2a = local_2a + -1;
      if (local_2a == 0) break;
      plVar1 = *(longlong **)(*(longlong *)(*(longlong *)(param_1 + 0x90) + 0x770) + 0x4e0);
      (**(code **)(*plVar1 + 0x18))(plVar1,local_40,local_2a);
    } while (*(short *)(local_40[0] + 2) != 0x58);
    plVar1 = *(longlong **)(*(longlong *)(*(longlong *)(param_1 + 0x90) + 0x770) + 0x4e0);
    (**(code **)(*plVar1 + 0x18))(plVar1,&local_50,local_2a);
    FUN_00414400(&local_48,local_50,5,0xf9);
    FUN_008bde10(*(undefined8 *)(param_1 + 0x90),local_48,DAT_00968f70);
    DAT_00968ff8 = (**(code **)(*DAT_00968f70 + 0x60))(DAT_00968f70);
  }
  else if (DAT_00969013 == '\x03') {
    (**(code **)(*DAT_00968f58 + 0x10))(DAT_00968f58,DAT_00968f60);
    sVar2 = (**(code **)(*DAT_00968f58 + 0x48))();
    local_2e = 0;
    do {
      local_20 = FUN_005b4690(DAT_00968f68,local_2e);
      local_28 = FUN_005b4690(DAT_00968f58,local_2e);
      sVar3 = (**(code **)(*DAT_00968f58 + 0x60))();
      local_2c = 0;
      sVar3 = sVar3 * 3 + -2;
      do {
        *(char *)(local_28 + (ulonglong)local_2c) =
             (char)((uint)*(byte *)(local_28 + (ulonglong)local_2c) +
                    (uint)*(byte *)(local_20 + (ulonglong)local_2c) + 1 >> 1);
        local_2c = local_2c + 1;
        sVar3 = sVar3 + -1;
      } while (sVar3 != 0);
      local_2e = local_2e + 1;
      sVar2 = sVar2 + -1;
    } while (sVar2 != 0);
  }
  else if (DAT_00969013 == '\x02') {
    (**(code **)(*DAT_00968f58 + 0x10))(DAT_00968f58,DAT_00968f50);
  }
  else if (DAT_00969013 == '\x01') {
    (**(code **)(*DAT_00968f58 + 0x10))(DAT_00968f58,DAT_00968f68);
  }
  else if (DAT_00969013 == '\0') {
    (**(code **)(*DAT_00968f58 + 0x10))(DAT_00968f58,DAT_00968f60);
  }
  if (DAT_00969013 == '\x04') {
    (**(code **)(*DAT_00968f58 + 0x10))(DAT_00968f58,DAT_00968f70);
  }
  iVar4 = (**(code **)(*DAT_00968f58 + 0x60))(DAT_00968f58);
  if (iVar4 < (int)(uint)DAT_00968ff8) {
    FUN_00864310(DAT_00968f58,DAT_00968f58,DAT_00968ff8,DAT_00968ffa);
  }
  FUN_00412a30(&local_50,3);
  return;
}

/* ==================================================
 * Function: FUN_008c3240
 * Address:  008c3240
 * Namespace: Global
 * ================================================== */

void FUN_008c3240(void)

{
  longlong *plVar1;
  short sVar2;
  int iVar3;
  int iVar4;
  undefined8 local_78;
  undefined8 local_70;
  longlong *local_68;
  uint local_54;
  int local_50;
  int local_4c;
  longlong *local_48;
  longlong local_40;
  longlong local_38;
  ushort local_2c;
  ushort local_2a;
  ushort local_28;
  ushort local_26;
  int local_24;
  int local_20;
  int local_1c;
  
  local_78 = 0;
  local_70 = 0;
  FUN_005f0770(*(undefined8 *)(DAT_00968e60 + 0x808),&local_70);
  sVar2 = FUN_0043b040(local_70);
  local_2c = sVar2 * 3;
  FUN_005f0770(*(undefined8 *)(DAT_00968e60 + 0xa48),&local_78);
  local_1c = FUN_0043b040(local_78);
  local_48 = (longlong *)FUN_005b31e0(PTR_PTR_005a1410,1);
  (**(code **)(*local_48 + 0x10))(local_48,DAT_00968fa0);
  local_2a = (ushort)(local_1c >> 0x1f);
  local_2a = ((ushort)local_1c ^ local_2a) - local_2a;
  local_4c = local_1c * local_1c;
  if (local_1c < 1) {
    for (; (int)(uint)local_2a < (int)((uint)DAT_00968e70 + local_1c); local_2a = local_2a + 1) {
      local_38 = FUN_005b4690(DAT_00968fa0,local_2a);
      local_26 = (ushort)(local_1c * 3 >> 0x1f);
      for (local_26 = ((ushort)(local_1c * 3) ^ local_26) - local_26;
          (int)(uint)local_26 < (int)(((uint)DAT_00968e6e + local_1c) * 3); local_26 = local_26 + 3)
      {
        if (local_2c <= *(byte *)(local_38 + (ulonglong)local_26)) {
          local_54 = 0;
          local_20 = local_1c;
          if (local_1c <= -local_1c) {
            iVar4 = local_1c * -2 + 1;
            do {
              local_40 = FUN_005b4690(local_48,(uint)local_2a + local_20);
              local_24 = local_1c;
              if (local_1c <= -local_1c) {
                iVar3 = local_1c * -2 + 1;
                do {
                  if (local_20 * local_20 + local_24 * local_24 <= local_4c) {
                    local_28 = local_26 + (short)local_24 * 3;
                    if (*(byte *)(local_40 + (ulonglong)local_28) < local_2c) {
                      local_54 = local_54 + *(byte *)(local_40 + (ulonglong)local_28);
                    }
                  }
                  local_24 = local_24 + 1;
                  iVar3 = iVar3 + -1;
                } while (iVar3 != 0);
              }
              local_20 = local_20 + 1;
              iVar4 = iVar4 + -1;
            } while (iVar4 != 0);
          }
          if (0 < (int)local_54) {
            *(char *)(local_38 + (ulonglong)local_26) = (char)local_2c + -1;
            *(undefined1 *)(local_38 + (ulonglong)(local_26 + 2)) = 0x7f;
          }
        }
      }
    }
  }
  else {
    for (; (int)(uint)local_2a < (int)((uint)DAT_00968e70 - local_1c); local_2a = local_2a + 1) {
      local_38 = FUN_005b4690(DAT_00968fa0,local_2a);
      for (local_26 = (short)local_1c * 3;
          (int)(uint)local_26 < (int)(((uint)DAT_00968e6e - local_1c) * 3); local_26 = local_26 + 3)
      {
        if (*(byte *)(local_38 + (ulonglong)local_26) <= local_2c) {
          local_50 = 0;
          local_54 = 0;
          local_20 = -local_1c;
          if (local_20 <= local_1c) {
            iVar4 = local_1c * 2 + 1;
            do {
              local_40 = FUN_005b4690(local_48,(uint)local_2a + local_20);
              local_24 = -local_1c;
              if (local_24 <= local_1c) {
                iVar3 = local_1c * 2 + 1;
                do {
                  if (local_20 * local_20 + local_24 * local_24 <= local_4c) {
                    local_28 = local_26 + (short)local_24 * 3;
                    if (local_2c <= *(byte *)(local_40 + (ulonglong)local_28)) {
                      local_50 = local_50 +
                                 (uint)*(byte *)(local_40 + (ulonglong)(local_28 + 2)) *
                                 (uint)*(byte *)(local_40 + (ulonglong)local_28);
                      local_54 = local_54 + *(byte *)(local_40 + (ulonglong)local_28);
                    }
                  }
                  local_24 = local_24 + 1;
                  iVar3 = iVar3 + -1;
                } while (iVar3 != 0);
              }
              local_20 = local_20 + 1;
              iVar4 = iVar4 + -1;
            } while (iVar4 != 0);
          }
          if (0 < (int)local_54) {
            *(char *)(local_38 + (ulonglong)local_26) = (char)local_2c + '\x01';
            *(char *)(local_38 + (ulonglong)(local_26 + 2)) =
                 (char)((int)((local_54 >> 1) + local_50) / (int)local_54);
          }
        }
      }
    }
  }
  plVar1 = local_48;
  local_68 = local_48;
  local_48 = (longlong *)0x0;
  FUN_0040f6e0(plVar1);
  FUN_00412a30(&local_78,2);
  return;
}

/* ==================================================
 * Function: FUN_008c3650
 * Address:  008c3650
 * Namespace: Global
 * ================================================== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

void FUN_008c3650(longlong param_1)

{
  undefined1 uVar1;
  short sVar2;
  short sVar3;
  ushort uVar4;
  longlong lVar5;
  longlong lVar6;
  undefined2 local_1e;
  undefined2 local_1a;
  
  *(ushort *)(param_1 + 0x6e) = (ushort)DAT_00968e72;
  *(short *)(param_1 + 0x6c) = 100 - *(short *)(param_1 + 0x6e);
  sVar2 = (**(code **)(*DAT_00968fa0 + 0x48))(DAT_00968fa0);
  local_1e = 0xf;
  if (0xe < (ushort)(sVar2 - 0x10U)) {
    sVar2 = sVar2 + -0x1e;
    do {
      lVar5 = FUN_005b4690(DAT_00968fa0,local_1e);
      lVar6 = FUN_005b4690(DAT_00968ef0,local_1e);
      sVar3 = (**(code **)(*DAT_00968fa0 + 0x60))(DAT_00968fa0);
      local_1a = 0xf;
      if (0xe < (ushort)(sVar3 - 0x10U)) {
        sVar3 = sVar3 + -0x1e;
        do {
          uVar4 = local_1a * 3 + 2;
          uVar1 = FUN_0040c470((double)((uint)*(byte *)(lVar5 + (ulonglong)uVar4) *
                                        (uint)*(ushort *)(param_1 + 0x6c) +
                                       (uint)*(byte *)(lVar6 + (ulonglong)uVar4) *
                                       (uint)*(ushort *)(param_1 + 0x6e)) / _DAT_008c37a0);
          *(undefined1 *)(lVar5 + (ulonglong)uVar4) = uVar1;
          local_1a = local_1a + 1;
          sVar3 = sVar3 + -1;
        } while (sVar3 != 0);
      }
      local_1e = local_1e + 1;
      sVar2 = sVar2 + -1;
    } while (sVar2 != 0);
  }
  return;
}

/* ==================================================
 * Function: FUN_008c37b0
 * Address:  008c37b0
 * Namespace: Global
 * ================================================== */

void FUN_008c37b0(longlong param_1)

{
  bool bVar1;
  ushort uVar2;
  short sVar3;
  short sVar4;
  longlong *plVar5;
  longlong lVar6;
  longlong lVar7;
  longlong lVar8;
  longlong lVar9;
  longlong lVar10;
  longlong lVar11;
  longlong lVar12;
  longlong lVar13;
  longlong lVar14;
  longlong lVar15;
  longlong lVar16;
  longlong lVar17;
  longlong lVar18;
  longlong lVar19;
  undefined2 local_9c;
  undefined2 local_9a;
  undefined2 local_1e;
  undefined2 local_1c;
  
  plVar5 = (longlong *)FUN_005b31e0(PTR_PTR_005a1410,1);
  (**(code **)(*plVar5 + 0x10))(plVar5,DAT_00968fa0);
  sVar3 = (**(code **)(*plVar5 + 0x48))(plVar5);
  local_1e = 10;
  if (9 < (ushort)(sVar3 - 0xbU)) {
    sVar3 = sVar3 + -0x14;
    do {
      lVar6 = FUN_005b4690(DAT_00968fa0,local_1e);
      lVar7 = FUN_005b4690(plVar5,local_1e - 9);
      lVar8 = FUN_005b4690(plVar5,local_1e - 6);
      lVar9 = FUN_005b4690(plVar5,local_1e - 4);
      lVar10 = FUN_005b4690(plVar5,local_1e - 3);
      lVar11 = FUN_005b4690(plVar5,local_1e - 2);
      lVar12 = FUN_005b4690(plVar5,local_1e - 1);
      lVar13 = FUN_005b4690(plVar5,local_1e);
      lVar14 = FUN_005b4690(plVar5,local_1e + 1);
      lVar15 = FUN_005b4690(plVar5,local_1e + 2);
      lVar16 = FUN_005b4690(plVar5,local_1e + 3);
      lVar17 = FUN_005b4690(plVar5,local_1e + 4);
      lVar18 = FUN_005b4690(plVar5,local_1e + 6);
      lVar19 = FUN_005b4690(plVar5,local_1e + 9);
      sVar4 = (**(code **)(*plVar5 + 0x60))(plVar5);
      local_1c = 10;
      if (9 < (ushort)(sVar4 - 0xbU)) {
        sVar4 = sVar4 + -0x14;
        do {
          uVar2 = local_1c * 3;
          local_9a = 0;
          bVar1 = *(byte *)(param_1 + 0x6b) < *(byte *)(lVar11 + (ulonglong)uVar2);
          if (bVar1) {
            local_9a = (ushort)*(byte *)(lVar11 + (ulonglong)(uVar2 + 2));
          }
          local_9c = (ushort)bVar1;
          if (*(byte *)(param_1 + 0x6b) < *(byte *)(lVar12 + (ulonglong)(uVar2 + 3))) {
            local_9c = local_9c + 1;
            local_9a = local_9a + *(byte *)(lVar12 + (ulonglong)(uVar2 + 5));
          }
          if (*(byte *)(param_1 + 0x6b) < *(byte *)(lVar13 + (ulonglong)(uVar2 + 6))) {
            local_9c = local_9c + 1;
            local_9a = local_9a + *(byte *)(lVar13 + (ulonglong)(uVar2 + 8));
          }
          if (*(byte *)(param_1 + 0x6b) < *(byte *)(lVar14 + (ulonglong)(uVar2 + 3))) {
            local_9c = local_9c + 1;
            local_9a = local_9a + *(byte *)(lVar14 + (ulonglong)(uVar2 + 5));
          }
          if (*(byte *)(param_1 + 0x6b) < *(byte *)(lVar15 + (ulonglong)uVar2)) {
            local_9c = local_9c + 1;
            local_9a = local_9a + *(byte *)(lVar15 + (ulonglong)(uVar2 + 2));
          }
          if (*(byte *)(param_1 + 0x6b) < *(byte *)(lVar14 + (int)(uVar2 - 3))) {
            local_9c = local_9c + 1;
            local_9a = local_9a + *(byte *)(lVar14 + (int)(uVar2 - 1));
          }
          if (*(byte *)(param_1 + 0x6b) < *(byte *)(lVar13 + (int)(uVar2 - 6))) {
            local_9c = local_9c + 1;
            local_9a = local_9a + *(byte *)(lVar13 + (int)(uVar2 - 4));
          }
          if (*(byte *)(param_1 + 0x6b) < *(byte *)(lVar12 + (int)(uVar2 - 3))) {
            local_9c = local_9c + 1;
            local_9a = local_9a + *(byte *)(lVar12 + (int)(uVar2 - 1));
          }
          if (local_9c < 3) {
            if (*(byte *)(param_1 + 0x6b) < *(byte *)(lVar10 + (ulonglong)uVar2)) {
              local_9c = local_9c + 1;
              local_9a = local_9a + *(byte *)(lVar10 + (ulonglong)(uVar2 + 2));
            }
            if (*(byte *)(param_1 + 0x6b) < *(byte *)(lVar11 + (ulonglong)(uVar2 + 6))) {
              local_9c = local_9c + 1;
              local_9a = local_9a + *(byte *)(lVar11 + (ulonglong)(uVar2 + 8));
            }
            if (*(byte *)(param_1 + 0x6b) < *(byte *)(lVar13 + (ulonglong)(uVar2 + 9))) {
              local_9c = local_9c + 1;
              local_9a = local_9a + *(byte *)(lVar13 + (ulonglong)(uVar2 + 0xb));
            }
            if (*(byte *)(param_1 + 0x6b) < *(byte *)(lVar15 + (ulonglong)(uVar2 + 6))) {
              local_9c = local_9c + 1;
              local_9a = local_9a + *(byte *)(lVar15 + (ulonglong)(uVar2 + 8));
            }
            if (*(byte *)(param_1 + 0x6b) < *(byte *)(lVar16 + (ulonglong)uVar2)) {
              local_9c = local_9c + 1;
              local_9a = local_9a + *(byte *)(lVar16 + (ulonglong)(uVar2 + 2));
            }
            if (*(byte *)(param_1 + 0x6b) < *(byte *)(lVar15 + (int)(uVar2 - 6))) {
              local_9c = local_9c + 1;
              local_9a = local_9a + *(byte *)(lVar15 + (int)(uVar2 - 4));
            }
            if (*(byte *)(param_1 + 0x6b) < *(byte *)(lVar13 + (int)(uVar2 - 9))) {
              local_9c = local_9c + 1;
              local_9a = local_9a + *(byte *)(lVar13 + (int)(uVar2 - 7));
            }
            if (*(byte *)(param_1 + 0x6b) < *(byte *)(lVar11 + (int)(uVar2 - 6))) {
              local_9c = local_9c + 1;
              local_9a = local_9a + *(byte *)(lVar11 + (int)(uVar2 - 4));
            }
          }
          if (local_9c < 3) {
            if (*(byte *)(param_1 + 0x6b) < *(byte *)(lVar8 + (ulonglong)uVar2)) {
              local_9c = local_9c + 1;
              local_9a = local_9a + *(byte *)(lVar8 + (ulonglong)(uVar2 + 2));
            }
            if (*(byte *)(param_1 + 0x6b) < *(byte *)(lVar9 + (ulonglong)(uVar2 + 0xc))) {
              local_9c = local_9c + 1;
              local_9a = local_9a + *(byte *)(lVar9 + (ulonglong)(uVar2 + 0xe));
            }
            if (*(byte *)(param_1 + 0x6b) < *(byte *)(lVar13 + (ulonglong)(uVar2 + 0x12))) {
              local_9c = local_9c + 1;
              local_9a = local_9a + *(byte *)(lVar13 + (ulonglong)(uVar2 + 0x14));
            }
            if (*(byte *)(param_1 + 0x6b) < *(byte *)(lVar17 + (ulonglong)(uVar2 + 0xc))) {
              local_9c = local_9c + 1;
              local_9a = local_9a + *(byte *)(lVar17 + (ulonglong)(uVar2 + 0xe));
            }
            if (*(byte *)(param_1 + 0x6b) < *(byte *)(lVar18 + (ulonglong)uVar2)) {
              local_9c = local_9c + 1;
              local_9a = local_9a + *(byte *)(lVar18 + (ulonglong)(uVar2 + 2));
            }
            if (*(byte *)(param_1 + 0x6b) < *(byte *)(lVar17 + (int)(uVar2 - 0xc))) {
              local_9c = local_9c + 1;
              local_9a = local_9a + *(byte *)(lVar17 + (int)(uVar2 - 10));
            }
            if (*(byte *)(param_1 + 0x6b) < *(byte *)(lVar13 + (int)(uVar2 - 0x12))) {
              local_9c = local_9c + 1;
              local_9a = local_9a + *(byte *)(lVar13 + (int)(uVar2 - 0x10));
            }
            if (*(byte *)(param_1 + 0x6b) < *(byte *)(lVar9 + (int)(uVar2 - 0xc))) {
              local_9c = local_9c + 1;
              local_9a = local_9a + *(byte *)(lVar9 + (int)(uVar2 - 10));
            }
          }
          if (local_9c < 3) {
            if (*(byte *)(param_1 + 0x6b) < *(byte *)(lVar7 + (ulonglong)uVar2)) {
              local_9c = local_9c + 1;
              local_9a = local_9a + *(byte *)(lVar7 + (ulonglong)(uVar2 + 2));
            }
            if (*(byte *)(param_1 + 0x6b) < *(byte *)(lVar8 + (ulonglong)(uVar2 + 0x12))) {
              local_9c = local_9c + 1;
              local_9a = local_9a + *(byte *)(lVar8 + (ulonglong)(uVar2 + 0x14));
            }
            if (*(byte *)(param_1 + 0x6b) < *(byte *)(lVar13 + (ulonglong)(uVar2 + 0x1b))) {
              local_9c = local_9c + 1;
              local_9a = local_9a + *(byte *)(lVar13 + (ulonglong)(uVar2 + 0x1d));
            }
            if (*(byte *)(param_1 + 0x6b) < *(byte *)(lVar18 + (ulonglong)(uVar2 + 0x12))) {
              local_9c = local_9c + 1;
              local_9a = local_9a + *(byte *)(lVar18 + (ulonglong)(uVar2 + 0x14));
            }
            if (*(byte *)(param_1 + 0x6b) < *(byte *)(lVar19 + (ulonglong)uVar2)) {
              local_9c = local_9c + 1;
              local_9a = local_9a + *(byte *)(lVar19 + (ulonglong)(uVar2 + 2));
            }
            if (*(byte *)(param_1 + 0x6b) < *(byte *)(lVar18 + (int)(uVar2 - 0x12))) {
              local_9c = local_9c + 1;
              local_9a = local_9a + *(byte *)(lVar18 + (int)(uVar2 - 0x10));
            }
            if (*(byte *)(param_1 + 0x6b) < *(byte *)(lVar13 + (int)(uVar2 - 0x1b))) {
              local_9c = local_9c + 1;
              local_9a = local_9a + *(byte *)(lVar13 + (int)(uVar2 - 0x19));
            }
            if (*(byte *)(param_1 + 0x6b) < *(byte *)(lVar8 + (int)(uVar2 - 0x12))) {
              local_9c = local_9c + 1;
              local_9a = local_9a + *(byte *)(lVar8 + (int)(uVar2 - 0x10));
            }
          }
          if (1 < local_9c) {
            *(char *)(lVar6 + (ulonglong)uVar2) = *(char *)(param_1 + 0x6b) + '\x01';
            *(char *)(lVar6 + (ulonglong)(uVar2 + 2)) = (char)(local_9a / local_9c);
          }
          local_1c = local_1c + 1;
          sVar4 = sVar4 + -1;
        } while (sVar4 != 0);
      }
      local_1e = local_1e + 1;
      sVar3 = sVar3 + -1;
    } while (sVar3 != 0);
  }
  FUN_0040f6e0(plVar5);
  return;
}

/* ==================================================
 * Function: FUN_008c4290
 * Address:  008c4290
 * Namespace: Global
 * ================================================== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

void FUN_008c4290(longlong param_1)

{
  char cVar1;
  undefined1 uVar2;
  short sVar3;
  short sVar4;
  longlong *plVar5;
  undefined1 auStack_88 [40];
  undefined8 local_60 [2];
  longlong local_50;
  longlong local_48;
  longlong local_40;
  longlong local_38;
  longlong local_30;
  short local_24;
  short local_22;
  ushort local_20;
  byte local_1d;
  ushort local_1c;
  ushort local_1a;
  
  local_60[0] = 0;
  FUN_005f0770(*(undefined8 *)(*(longlong *)(param_1 + 0x90) + 0x808),local_60);
  cVar1 = FUN_0043b040(local_60[0]);
  local_1d = cVar1 * '\x03';
  if (5 < local_1d) {
    FUN_008c37b0(auStack_88);
  }
  if (DAT_00968e72 != 0) {
    FUN_008c3650(auStack_88);
  }
  (**(code **)(*DAT_00968f78 + 0x10))(DAT_00968f78,DAT_00968f98);
  FUN_008638e0(DAT_00968f78,&DAT_007f7f7f);
  sVar3 = (**(code **)(*DAT_00968f98 + 0x48))(DAT_00968f98);
  local_24 = 5;
  if (4 < (ushort)(sVar3 - 6U)) {
    sVar3 = sVar3 + -10;
    do {
      local_50 = FUN_005b4690(DAT_00968fa0,local_24);
      local_48 = FUN_005b4690(DAT_00968f78,local_24);
      local_40 = FUN_005b4690(DAT_00968f98,local_24);
      local_38 = FUN_005b4690(DAT_00968f58,local_24);
      local_30 = FUN_005b4690(DAT_00968f98,local_24);
      sVar4 = (**(code **)(*DAT_00968f98 + 0x60))(DAT_00968f98);
      local_22 = 5;
      if (4 < (ushort)(sVar4 - 6U)) {
        sVar4 = sVar4 + -10;
        do {
          local_20 = local_22 * 3;
          if ((local_1d < *(byte *)(local_50 + (ulonglong)local_20)) ||
             (*(char *)(local_50 + (ulonglong)(local_20 + 2)) == -1)) {
            FUN_00409900(PTR_DAT_00952770 +
                         (ulonglong)*(byte *)(local_50 + (ulonglong)(local_20 + 2)) * 3,
                         local_48 + (ulonglong)local_20,3);
          }
          else {
            local_1c = FUN_0040c470((double)((uint)*(byte *)(local_50 + (ulonglong)local_20) * 0x1fe
                                            ) /
                                    (double)((uint)local_1d +
                                            (uint)*(byte *)(local_50 + (ulonglong)local_20)));
            local_1a = 0xff - local_1c;
            uVar2 = FUN_0040c470((double)((uint)*(byte *)(local_30 + (ulonglong)local_20) *
                                          (uint)local_1c +
                                         (uint)*(byte *)(local_38 + (ulonglong)local_20) *
                                         (uint)local_1a) / _DAT_008c4740);
            *(undefined1 *)(local_40 + (ulonglong)local_20) = uVar2;
            uVar2 = FUN_0040c470((double)((uint)*(byte *)(local_30 + (ulonglong)(local_20 + 1)) *
                                          (uint)local_1c +
                                         (uint)*(byte *)(local_38 + (ulonglong)(local_20 + 1)) *
                                         (uint)local_1a) / _DAT_008c4740);
            *(undefined1 *)(local_40 + (ulonglong)(local_20 + 1)) = uVar2;
            uVar2 = FUN_0040c470((double)((uint)*(byte *)(local_30 + (ulonglong)(local_20 + 2)) *
                                          (uint)local_1c +
                                         (uint)*(byte *)(local_38 + (ulonglong)(local_20 + 2)) *
                                         (uint)local_1a) / _DAT_008c4740);
            *(undefined1 *)(local_40 + (ulonglong)(local_20 + 2)) = uVar2;
            *(undefined1 *)(local_50 + (ulonglong)(local_20 + 2)) = 0x7f;
          }
          local_22 = local_22 + 1;
          sVar4 = sVar4 + -1;
        } while (sVar4 != 0);
      }
      local_24 = local_24 + 1;
      sVar3 = sVar3 + -1;
    } while (sVar3 != 0);
  }
  if (DAT_00968e72 != 0) {
    local_1a = (ushort)DAT_00968e72;
    local_1c = 100 - local_1a;
    sVar3 = (**(code **)(*DAT_00968f98 + 0x48))();
    local_24 = 0;
    do {
      local_40 = FUN_005b4690(DAT_00968f98,local_24);
      local_38 = FUN_005b4690(DAT_00968ee8,local_24);
      sVar4 = (**(code **)(*DAT_00968f98 + 0x60))();
      local_20 = 0;
      sVar4 = (sVar4 + -1) * 3 + 1;
      do {
        uVar2 = FUN_0040c470((double)((uint)*(byte *)(local_40 + (ulonglong)local_20) *
                                      (uint)local_1c +
                                     (uint)*(byte *)(local_38 + (ulonglong)local_20) *
                                     (uint)local_1a) / _DAT_008c4748);
        *(undefined1 *)(local_40 + (ulonglong)local_20) = uVar2;
        local_20 = local_20 + 1;
        sVar4 = sVar4 + -1;
      } while (sVar4 != 0);
      local_24 = local_24 + 1;
      sVar3 = sVar3 + -1;
    } while (sVar3 != 0);
  }
  plVar5 = (longlong *)
           FUN_005ae7d0(*(undefined8 *)
                         (*(longlong *)(*(longlong *)PTR_DAT_00952838 + 0x738) + 0x338));
  (**(code **)(*plVar5 + 0x10))(plVar5,DAT_00968f98);
  FUN_00412950(local_60);
  return;
}

/* ==================================================
 * Function: FUN_008c4770
 * Address:  008c4770
 * Namespace: Global
 * ================================================== */

void FUN_008c4770(longlong param_1)

{
  uint uVar1;
  short sVar2;
  short sVar3;
  undefined8 local_70 [3];
  ushort local_58;
  ushort local_56;
  ushort local_54;
  ushort local_52;
  longlong local_50;
  longlong local_48;
  longlong local_40;
  longlong local_38;
  longlong local_30;
  longlong local_28;
  short local_20;
  ushort local_1e;
  ushort local_1c;
  short local_1a;
  
  local_70[0] = 0;
  FUN_005f0770(*(undefined8 *)(*(longlong *)(param_1 + 0x90) + 0x808),local_70);
  local_1a = FUN_0043b040(local_70[0]);
  local_52 = local_1a * 3;
  sVar2 = (**(code **)(*DAT_00968f98 + 0x48))(DAT_00968f98);
  local_1e = 3;
  if (2 < (ushort)(sVar2 - 4U)) {
    sVar2 = sVar2 + -6;
    do {
      local_48 = FUN_005b4690(DAT_00968f98,local_1e);
      local_50 = FUN_005b4690(DAT_00968f88,local_1e);
      local_40 = FUN_005b4690(DAT_00968f58,local_1e);
      local_30 = FUN_005b4690(DAT_00968fa0,local_1e - 2);
      local_28 = FUN_005b4690(DAT_00968fa0,local_1e);
      local_38 = FUN_005b4690(DAT_00968fa0);
      sVar3 = (**(code **)(*DAT_00968f98 + 0x60))(DAT_00968f98);
      local_20 = 3;
      if (2 < (ushort)(sVar3 - 4U)) {
        sVar3 = sVar3 + -6;
        do {
          local_1c = local_20 * 3;
          if (*(byte *)(local_28 + (ulonglong)local_1c) < local_52) {
            uVar1 = ((uint)*(byte *)(local_28 + (ulonglong)local_1c) * 0x80 -
                    (uint)*(byte *)(local_28 + (ulonglong)local_1c)) / (uint)local_52;
            local_54 = (ushort)uVar1;
            local_56 = local_54 >> 1;
            local_58 = 0xff - (local_54 + local_56);
            *(char *)(local_48 + (ulonglong)local_1c) =
                 (char)((ulonglong)
                        ((uint)*(byte *)(local_48 + (ulonglong)local_1c) * (uVar1 & 0xffff) +
                         (uint)*(byte *)(local_50 + (ulonglong)local_1c) * (uint)local_56 +
                        (uint)*(byte *)(local_40 + (ulonglong)local_1c) * (uint)local_58) / 0xff);
            *(char *)(local_48 + (ulonglong)(local_1c + 1)) =
                 (char)((ulonglong)
                        ((uint)*(byte *)(local_48 + (ulonglong)(local_1c + 1)) * (uVar1 & 0xffff) +
                         (uint)*(byte *)(local_50 + (ulonglong)(local_1c + 1)) * (uint)local_56 +
                        (uint)*(byte *)(local_40 + (ulonglong)(local_1c + 1)) * (uint)local_58) /
                       0xff);
            *(char *)(local_48 + (ulonglong)(local_1c + 2)) =
                 (char)((ulonglong)
                        ((uint)*(byte *)(local_48 + (ulonglong)(local_1c + 2)) * (uVar1 & 0xffff) +
                         (uint)*(byte *)(local_50 + (ulonglong)(local_1c + 2)) * (uint)local_56 +
                        (uint)*(byte *)(local_40 + (ulonglong)(local_1c + 2)) * (uint)local_58) /
                       0xff);
            *(char *)(local_28 + (ulonglong)local_1c) =
                 (char)((ulonglong)
                        (((uint)*(byte *)(local_30 + (int)(local_1c - 6)) +
                          (uint)*(byte *)(local_30 + (ulonglong)(local_1c + 6)) +
                          (uint)*(byte *)(local_38 + (int)(local_1c - 6)) +
                         (uint)*(byte *)(local_38 + (ulonglong)(local_1c + 6))) * 2 +
                         ((uint)*(byte *)(local_28 + (int)(local_1c - 6)) +
                          (uint)*(byte *)(local_30 + (ulonglong)local_1c) +
                          (uint)*(byte *)(local_28 + (ulonglong)(local_1c + 6)) +
                         (uint)*(byte *)(local_38 + (ulonglong)local_1c)) * 3 +
                        (uint)*(byte *)(local_28 + (ulonglong)local_1c) * 4) / 0x18);
            *(char *)(local_28 + (ulonglong)(local_1c + 2)) =
                 (char)((ulonglong)
                        (((uint)*(byte *)(local_30 + (int)(local_1c - 4)) +
                          (uint)*(byte *)(local_30 + (ulonglong)(local_1c + 8)) +
                          (uint)*(byte *)(local_38 + (int)(local_1c - 4)) +
                         (uint)*(byte *)(local_38 + (ulonglong)(local_1c + 8))) * 2 +
                         ((uint)*(byte *)(local_28 + (int)(local_1c - 4)) +
                          (uint)*(byte *)(local_30 + (ulonglong)(local_1c + 2)) +
                          (uint)*(byte *)(local_28 + (ulonglong)(local_1c + 8)) +
                         (uint)*(byte *)(local_38 + (ulonglong)(local_1c + 2))) * 3 +
                        (uint)*(byte *)(local_28 + (ulonglong)(local_1c + 2)) * 4) / 0x18);
          }
          local_20 = local_20 + 1;
          sVar3 = sVar3 + -1;
        } while (sVar3 != 0);
      }
      local_1e = local_1e + 1;
      sVar2 = sVar2 + -1;
    } while (sVar2 != 0);
  }
  FUN_00412950(local_70);
  return;
}

/* ==================================================
 * Function: FUN_0085f120
 * Address:  0085f120
 * Namespace: Global
 * ================================================== */

void FUN_0085f120(undefined8 param_1,undefined8 param_2,undefined8 param_3)

{
  undefined8 uVar1;
  longlong *plVar2;
  undefined8 local_res10;
  undefined8 local_res18;
  undefined1 auStack_88 [32];
  undefined8 local_68;
  undefined8 local_60;
  longlong *local_58;
  longlong *local_50;
  longlong *local_48;
  undefined8 local_40;
  undefined8 local_38;
  longlong *local_30;
  longlong *local_28;
  longlong *local_20 [2];
  
  local_res10 = param_2;
  local_res18 = param_3;
  FUN_008638e0(param_2,0);
  local_20[0] = (longlong *)FUN_005b31e0(PTR_PTR_005a1410,1);
  (**(code **)(*local_20[0] + 0x10))(local_20[0],param_1);
  FUN_008644a0(param_1,local_20[0]);
  local_30 = (longlong *)FUN_005b31e0(PTR_PTR_005a1410,1);
  (**(code **)(*local_30 + 0x10))(local_30,local_20[0]);
  local_28 = (longlong *)FUN_005b31e0(PTR_PTR_005a1410,1);
  (**(code **)(*local_28 + 0x10))(local_28,local_20[0]);
  local_38 = FUN_005b31e0(PTR_PTR_005a1410,1);
  local_40 = FUN_005b31e0(PTR_PTR_005a1410,1);
  if (4 < DAT_0096257c) {
    FUN_0085dec0(&local_28,local_20,2);
  }
  FUN_0085ec00(auStack_88,local_20[0],local_28,local_30);
  if (DAT_0096257c == 1) {
LAB_0085f23f:
    FUN_0085dec0(&local_28,local_20,2);
  }
  else if (DAT_0096257c == 2) {
LAB_0085f251:
    FUN_0085dec0(&local_28,local_20,3);
  }
  else {
    if (DAT_0096257c == 3) goto LAB_0085f23f;
    if ((byte)(DAT_0096257c - 4) < 2) goto LAB_0085f251;
  }
  FUN_0085ec00(auStack_88,local_20[0],local_28,local_38);
  if (DAT_0096257c == 1) {
LAB_0085f297:
    FUN_0085dec0(&local_28,local_20,2);
  }
  else if (DAT_0096257c == 2) {
LAB_0085f2a9:
    FUN_0085dec0(&local_28,local_20,3);
  }
  else {
    if (DAT_0096257c == 3) goto LAB_0085f297;
    if ((byte)(DAT_0096257c - 4) < 2) goto LAB_0085f2a9;
  }
  FUN_0085ec00(auStack_88,local_20[0],local_28,local_40);
  FUN_0085ee70(auStack_88,local_30,0);
  FUN_0085ee70(auStack_88,local_38,1);
  FUN_0085ee70(auStack_88,local_40,2);
  if (DAT_0096257c == 1) {
LAB_0085f31c:
    FUN_0085e2a0(&local_res10,2,1);
    FUN_0085e2a0(&local_res10,4,2);
  }
  else {
    if (DAT_0096257c != 2) {
      if (DAT_0096257c == 3) goto LAB_0085f31c;
      if (1 < (byte)(DAT_0096257c - 4)) goto LAB_0085f362;
    }
    FUN_0085e2a0(&local_res10,3,1);
    FUN_0085e2a0(&local_res10,9,2);
  }
LAB_0085f362:
  if (4 < DAT_0096257c) {
    FUN_0085e2a0(&local_res10,2,0);
    FUN_0085e2a0(&local_res10,2,1);
    FUN_0085e2a0(&local_res10,2,2);
  }
  FUN_0085eb80(auStack_88,local_res10);
  plVar2 = local_20[0];
  local_48 = local_20[0];
  local_20[0] = (longlong *)0x0;
  FUN_0040f6e0(plVar2);
  plVar2 = local_28;
  local_50 = local_28;
  local_28 = (longlong *)0x0;
  FUN_0040f6e0(plVar2);
  plVar2 = local_30;
  local_58 = local_30;
  local_30 = (longlong *)0x0;
  FUN_0040f6e0(plVar2);
  uVar1 = local_38;
  local_60 = local_38;
  local_38 = 0;
  FUN_0040f6e0(uVar1);
  uVar1 = local_40;
  local_68 = local_40;
  local_40 = 0;
  FUN_0040f6e0(uVar1);
  return;
}

/* ==================================================
 * Function: FUN_0085ffb0
 * Address:  0085ffb0
 * Namespace: Global
 * ================================================== */

void FUN_0085ffb0(longlong *param_1,longlong *param_2,longlong *param_3,longlong *param_4,
                 short param_5,byte param_6)

{
  short sVar1;
  short sVar2;
  longlong lVar3;
  longlong lVar4;
  longlong lVar5;
  longlong lVar6;
  short local_1e;
  short local_1c;
  ushort local_1a;
  
  if (param_5 == 0) {
    (**(code **)(*param_2 + 0x10))(param_2,param_1);
    (**(code **)(*param_3 + 0x10))(param_3,param_1);
    (**(code **)(*param_4 + 0x10))(param_4,param_1);
    FUN_0085fe50(param_4,param_6);
  }
  else {
    sVar1 = (**(code **)(*param_1 + 0x48))();
    local_1c = 0;
    do {
      lVar3 = FUN_005b4690(param_1,local_1c);
      lVar4 = FUN_005b4690(param_2,local_1c);
      lVar5 = FUN_005b4690(param_3,local_1c);
      lVar6 = FUN_005b4690(param_4,local_1c);
      sVar2 = (**(code **)(*param_1 + 0x60))();
      local_1a = 0;
      sVar2 = sVar2 * 3 + -2;
      do {
        if (*(byte *)(lVar3 + (ulonglong)local_1a) < *(byte *)(lVar4 + (ulonglong)local_1a)) {
          *(undefined1 *)(lVar4 + (ulonglong)local_1a) =
               *(undefined1 *)(lVar3 + (ulonglong)local_1a);
        }
        if (*(byte *)(lVar5 + (ulonglong)local_1a) < *(byte *)(lVar3 + (ulonglong)local_1a)) {
          *(undefined1 *)(lVar5 + (ulonglong)local_1a) =
               *(undefined1 *)(lVar3 + (ulonglong)local_1a);
        }
        FUN_00409900(lVar6 + (ulonglong)((uint)local_1a * 2),&local_1e,2);
        local_1e = local_1e + (ushort)*(byte *)(lVar3 + (ulonglong)local_1a) / (ushort)param_6;
        FUN_00409900(&local_1e,lVar6 + (ulonglong)((uint)local_1a * 2),2);
        local_1a = local_1a + 1;
        sVar2 = sVar2 + -1;
      } while (sVar2 != 0);
      local_1c = local_1c + 1;
      sVar1 = sVar1 + -1;
    } while (sVar1 != 0);
  }
  return;
}

/* ==================================================
 * Function: FUN_0085ec00
 * Address:  0085ec00
 * Namespace: Global
 * ================================================== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

void FUN_0085ec00(undefined8 param_1,longlong *param_2,longlong *param_3,longlong *param_4)

{
  byte bVar1;
  short sVar2;
  short sVar3;
  ushort uVar4;
  int iVar5;
  longlong lVar6;
  longlong lVar7;
  longlong lVar8;
  longlong lVar9;
  longlong lVar10;
  short sVar11;
  ushort local_48;
  ushort local_46;
  undefined1 local_42;
  
  (**(code **)(*param_3 + 0x10))(param_3,param_2);
  (**(code **)(*param_4 + 0x10))(param_4,param_2);
  sVar2 = (**(code **)(*param_2 + 0x60))(param_2);
  sVar3 = (**(code **)(*param_2 + 0x48))(param_2);
  local_48 = 1;
  for (sVar3 = sVar3 + -2; sVar3 != 0; sVar3 = sVar3 + -1) {
    lVar6 = FUN_005b4690(param_2,local_48 - 1);
    lVar7 = FUN_005b4690(param_2,local_48);
    lVar8 = FUN_005b4690(param_2,local_48 + 1);
    lVar9 = FUN_005b4690(param_3,local_48);
    lVar10 = FUN_005b4690(param_4,local_48);
    local_46 = 1;
    for (sVar11 = sVar2 + -2; sVar11 != 0; sVar11 = sVar11 + -1) {
      uVar4 = FUN_0040c470((double)(((uint)*(byte *)(lVar6 + (ulonglong)local_46) +
                                     (uint)*(byte *)(lVar7 + (int)(local_46 - 1)) +
                                     (uint)*(byte *)(lVar7 + (ulonglong)(local_46 + 1)) +
                                    (uint)*(byte *)(lVar8 + (ulonglong)local_46)) * 4 +
                                   ((uint)*(byte *)(lVar6 + (int)(local_46 - 1)) +
                                    (uint)*(byte *)(lVar6 + (ulonglong)(local_46 + 1)) +
                                    (uint)*(byte *)(lVar8 + (int)(local_46 - 1)) +
                                   (uint)*(byte *)(lVar8 + (ulonglong)(local_46 + 1))) * 3) /
                           _DAT_0085ee60);
      local_42 = (undefined1)uVar4;
      *(undefined1 *)(lVar9 + (ulonglong)local_46) = local_42;
      iVar5 = (uint)*(byte *)(lVar7 + (ulonglong)local_46) - (uint)uVar4;
      bVar1 = (byte)(iVar5 >> 0x1f);
      *(byte *)(lVar10 + (ulonglong)local_46) = ((byte)iVar5 ^ bVar1) - bVar1;
      local_46 = local_46 + 1;
    }
    local_48 = local_48 + 1;
  }
  return;
}

/* ==================================================
 * Function: FUN_0085ee70
 * Address:  0085ee70
 * Namespace: Global
 * ================================================== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

void FUN_0085ee70(longlong param_1,longlong *param_2,byte param_3)

{
  double dVar1;
  undefined1 uVar2;
  short sVar3;
  short sVar4;
  ushort uVar5;
  longlong lVar6;
  longlong lVar7;
  longlong lVar8;
  longlong lVar9;
  ushort uVar10;
  ushort uVar11;
  double dVar12;
  
  dVar12 = (double)param_3 * _DAT_0085f110 + _DAT_0085f118;
  dVar1 = *(double *)(param_1 + 0xa0);
  sVar3 = (**(code **)(*param_2 + 0x48))(param_2);
  uVar10 = 1;
  for (sVar3 = sVar3 + -2; sVar3 != 0; sVar3 = sVar3 + -1) {
    lVar6 = FUN_005b4690(param_2,uVar10 - 1);
    lVar7 = FUN_005b4690(param_2,uVar10);
    lVar8 = FUN_005b4690(param_2,uVar10 + 1);
    lVar9 = FUN_005b4690(*(undefined8 *)(param_1 + 0x98),uVar10);
    sVar4 = (**(code **)(*param_2 + 0x60))(param_2);
    uVar11 = 1;
    for (sVar4 = sVar4 + -2; sVar4 != 0; sVar4 = sVar4 + -1) {
      uVar5 = FUN_0040c470(dVar1 * dVar12 *
                           (double)((uint)*(byte *)(lVar7 + (ulonglong)uVar11) * 4 +
                                    ((uint)*(byte *)(lVar6 + (ulonglong)uVar11) +
                                     (uint)*(byte *)(lVar8 + (ulonglong)uVar11) +
                                     (uint)*(byte *)(lVar7 + (int)(uVar11 - 1)) +
                                    (uint)*(byte *)(lVar7 + (ulonglong)(uVar11 + 1))) * 3 +
                                   ((uint)*(byte *)(lVar6 + (int)(uVar11 - 1)) +
                                    (uint)*(byte *)(lVar6 + (ulonglong)(uVar11 + 1)) +
                                    (uint)*(byte *)(lVar8 + (int)(uVar11 - 1)) +
                                   (uint)*(byte *)(lVar8 + (ulonglong)(uVar11 + 1))) * 2));
      uVar2 = FUN_0040c470((double)((ulonglong)uVar5 << 8) / (double)(uVar5 + 0x80));
      *(undefined1 *)(lVar9 + (ulonglong)((uint)uVar11 * 3 + (uint)param_3)) = uVar2;
      uVar11 = uVar11 + 1;
    }
    uVar10 = uVar10 + 1;
  }
  return;
}

/* ==================================================
 * Function: FUN_0085eb80
 * Address:  0085eb80
 * Namespace: Global
 * ================================================== */

void FUN_0085eb80(undefined8 param_1,undefined8 param_2)

{
  longlong *plVar1;
  undefined1 auStack_48 [32];
  longlong *local_28;
  longlong *local_20;
  
  local_20 = (longlong *)FUN_005b31e0(PTR_PTR_005a1410,1);
  (**(code **)(*local_20 + 0x10))(local_20,param_2);
  FUN_0085e4d0(auStack_48,0);
  FUN_0085e4d0(auStack_48,1);
  FUN_0085e4d0(auStack_48,2);
  plVar1 = local_20;
  local_28 = local_20;
  local_20 = (longlong *)0x0;
  FUN_0040f6e0(plVar1);
  return;
}

/* ==================================================
 * Function: FUN_0085dec0
 * Address:  0085dec0
 * Namespace: Global
 * ================================================== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

void FUN_0085dec0(undefined8 *param_1,undefined8 *param_2,char param_3)

{
  undefined1 uVar1;
  int iVar2;
  int iVar3;
  int iVar4;
  int iVar5;
  longlong lVar6;
  longlong lVar7;
  longlong lVar8;
  longlong lVar9;
  int iVar10;
  int iVar11;
  int iVar12;
  int local_24;
  int local_20;
  
  (**(code **)(*(longlong *)*param_2 + 0x10))((longlong *)*param_2,*param_1);
  FUN_008638e0(*param_2,0);
  iVar2 = (**(code **)(*(longlong *)*param_1 + 0x48))((longlong *)*param_1);
  iVar2 = iVar2 + param_3 + -1;
  iVar3 = iVar2 / (int)param_3;
  iVar4 = iVar3 + -1;
  iVar2 = (**(code **)(*(longlong *)*param_1 + 0x60))
                    ((longlong *)*param_1,(longlong)iVar2 % (longlong)(int)param_3 & 0xffffffff);
  iVar2 = (iVar2 + param_3 + -1) / (int)param_3;
  iVar5 = iVar2 + -1;
  if (param_3 == '\x02') {
    local_24 = 0;
    iVar12 = iVar4;
    if (-1 < iVar3 + -2) {
      do {
        lVar6 = FUN_005b4690(*param_2,local_24);
        lVar7 = FUN_005b4690(*param_1,local_24 * 2);
        lVar8 = FUN_005b4690(*param_1,local_24 * 2 + 1);
        local_20 = 0;
        iVar3 = iVar5;
        if (-1 < iVar2 + -2) {
          do {
            iVar10 = local_20 * 2;
            uVar1 = FUN_0040c470((double)((uint)*(byte *)(lVar7 + iVar10) +
                                          (uint)*(byte *)(lVar7 + (iVar10 + 1)) +
                                          (uint)*(byte *)(lVar8 + iVar10) +
                                         (uint)*(byte *)(lVar8 + (iVar10 + 1))) / _DAT_0085e290);
            *(undefined1 *)(lVar6 + local_20) = uVar1;
            local_20 = local_20 + 1;
            iVar3 = iVar3 + -1;
          } while (iVar3 != 0);
        }
        local_24 = local_24 + 1;
        iVar12 = iVar12 + -1;
      } while (iVar12 != 0);
    }
  }
  else if ((param_3 == '\x03') && (local_24 = 0, iVar12 = iVar4, -1 < iVar3 + -2)) {
    do {
      lVar6 = FUN_005b4690(*param_1,local_24 * 3);
      lVar7 = FUN_005b4690(*param_1,local_24 * 3 + 1);
      lVar8 = FUN_005b4690(*param_1,local_24 * 3 + 2);
      lVar9 = FUN_005b4690(*param_2,local_24);
      local_20 = 0;
      iVar3 = iVar5;
      if (-1 < iVar2 + -2) {
        do {
          iVar10 = local_20 * 3;
          iVar11 = iVar10 + 1;
          uVar1 = FUN_0040c470((double)((uint)*(byte *)(lVar7 + iVar11) +
                                        (uint)*(byte *)(lVar6 + iVar11) +
                                        (uint)*(byte *)(lVar7 + iVar10) +
                                        (uint)*(byte *)(lVar7 + (iVar10 + 2)) +
                                        (uint)*(byte *)(lVar8 + iVar11) +
                                        (uint)*(byte *)(lVar6 + iVar10) +
                                        (uint)*(byte *)(lVar6 + (iVar10 + 2)) +
                                        (uint)*(byte *)(lVar8 + iVar10) +
                                       (uint)*(byte *)(lVar8 + (iVar10 + 2))) / _DAT_0085e298);
          *(undefined1 *)(lVar9 + local_20) = uVar1;
          local_20 = local_20 + 1;
          iVar3 = iVar3 + -1;
        } while (iVar3 != 0);
      }
      local_24 = local_24 + 1;
      iVar12 = iVar12 + -1;
    } while (iVar12 != 0);
  }
  (**(code **)(*(longlong *)*param_2 + 0x70))((longlong *)*param_2,iVar4);
  (**(code **)(*(longlong *)*param_2 + 0x88))((longlong *)*param_2,iVar5);
  return;
}

/* ==================================================
 * Function: FUN_0085e2a0
 * Address:  0085e2a0
 * Namespace: Global
 * ================================================== */

void FUN_0085e2a0(undefined8 *param_1,byte param_2,byte param_3)

{
  undefined1 uVar1;
  short sVar2;
  ushort uVar3;
  ushort uVar4;
  longlong lVar5;
  longlong lVar6;
  longlong lVar7;
  double dVar8;
  double dVar9;
  ushort local_1e;
  
  sVar2 = (**(code **)(*(longlong *)*param_1 + 0x48))((longlong *)*param_1);
  uVar3 = sVar2 - 1;
  while (uVar3 != 0) {
    uVar3 = uVar3 - 1;
    lVar5 = FUN_005b4690(*param_1);
    dVar8 = (double)FUN_0040af40((double)uVar3 / (double)param_2,
                                 (ulonglong)uVar3 % (ulonglong)param_2);
    lVar6 = FUN_005b4690(*param_1,uVar3 / param_2);
    lVar7 = FUN_005b4690(*param_1);
    sVar2 = (**(code **)(*(longlong *)*param_1 + 0x60))((longlong *)*param_1);
    local_1e = 1;
    for (sVar2 = sVar2 + -2; sVar2 != 0; sVar2 = sVar2 + -1) {
      uVar4 = (local_1e / param_2) * 3 + (ushort)param_3;
      dVar9 = (double)FUN_0040af40((double)local_1e / (double)param_2,
                                   (ulonglong)local_1e % (ulonglong)param_2);
      uVar1 = FUN_0040c470(((double)*(byte *)(lVar6 + (ulonglong)uVar4) * (DAT_0085e4c8 - dVar9) +
                           (double)*(byte *)(lVar6 + (ulonglong)(uVar4 + 3)) * dVar9) *
                           (DAT_0085e4c8 - dVar8) +
                           ((double)*(byte *)(lVar7 + (ulonglong)uVar4) * (DAT_0085e4c8 - dVar9) +
                           (double)*(byte *)(lVar7 + (ulonglong)(uVar4 + 3)) * dVar9) * dVar8);
      *(undefined1 *)(lVar5 + (ulonglong)((uint)local_1e * 3 + (uint)param_3)) = uVar1;
      local_1e = local_1e + 1;
    }
  }
  return;
}

/* ==================================================
 * Function: FUN_0085fcc0
 * Address:  0085fcc0
 * Namespace: Global
 * ================================================== */

void FUN_0085fcc0(longlong *param_1,ushort param_2,char param_3)

{
  short sVar1;
  int iVar2;
  longlong *plVar3;
  longlong lVar4;
  longlong lVar5;
  short sVar6;
  ushort local_1e;
  short local_1c;
  ushort local_1a;
  
  plVar3 = (longlong *)FUN_005b31e0(PTR_PTR_005a1410,1);
  (**(code **)(*plVar3 + 0x10))(plVar3,param_1);
  FUN_008638e0(param_1,0);
  sVar1 = (**(code **)(*plVar3 + 0x48))();
  local_1c = 0;
  do {
    lVar4 = FUN_005b4690(plVar3,local_1c);
    lVar5 = FUN_005b4690(param_1,local_1c);
    iVar2 = (**(code **)(*plVar3 + 0x60))();
    local_1a = 0;
    sVar6 = (short)(iVar2 / 2) * 3 + -2;
    do {
      FUN_00409900(lVar4 + (ulonglong)((uint)local_1a * 2),&local_1e,2);
      *(char *)(lVar5 + (ulonglong)local_1a) =
           (char)(((uint)(byte)(param_2 >> 1) + (uint)local_1e) / (uint)param_2) * param_3;
      local_1a = local_1a + 1;
      sVar6 = sVar6 + -1;
    } while (sVar6 != 0);
    local_1c = local_1c + 1;
    sVar1 = sVar1 + -1;
  } while (sVar1 != 0);
  iVar2 = (**(code **)(*plVar3 + 0x60))(plVar3);
  (**(code **)(*param_1 + 0x88))(param_1,iVar2 / 2);
  FUN_0040f6e0(plVar3);
  return;
}

/* ==================================================
 * Function: FUN_0085e4d0
 * Address:  0085e4d0
 * Namespace: Global
 * ================================================== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

void FUN_0085e4d0(longlong param_1,byte param_2)

{
  byte bVar1;
  byte bVar2;
  byte bVar3;
  byte bVar4;
  undefined1 uVar5;
  short sVar6;
  short sVar7;
  ushort uVar8;
  longlong lVar9;
  longlong lVar10;
  longlong lVar11;
  longlong lVar12;
  longlong lVar13;
  longlong lVar14;
  longlong lVar15;
  longlong lVar16;
  undefined2 local_22;
  undefined2 local_1e;
  
  bVar1 = DAT_0096257c * (param_2 + 1);
  bVar2 = bVar1 * '\x03';
  bVar3 = bVar1 * '\x06';
  bVar4 = bVar1 * '\t';
  sVar6 = (**(code **)(**(longlong **)(param_1 + 0x28) + 0x48))(*(longlong **)(param_1 + 0x28));
  local_22 = (ushort)bVar3;
  if (local_22 <= (ushort)(sVar6 - (ushort)bVar3)) {
    sVar6 = ((sVar6 - (ushort)bVar3) - local_22) + 1;
    do {
      lVar9 = FUN_005b4690(*(undefined8 *)(param_1 + 0x28),(uint)local_22 + (uint)bVar1 * -3);
      lVar10 = FUN_005b4690(*(undefined8 *)(param_1 + 0x28),(uint)local_22 + (uint)bVar1 * -2);
      lVar11 = FUN_005b4690(*(undefined8 *)(param_1 + 0x28),(uint)local_22 - (uint)bVar1);
      lVar12 = FUN_005b4690(*(undefined8 *)(param_1 + 0x28),local_22);
      lVar13 = FUN_005b4690(*(undefined8 *)(param_1 + 0x28),(uint)local_22 + (uint)bVar1);
      lVar14 = FUN_005b4690(*(undefined8 *)(param_1 + 0x28),(uint)local_22 + (uint)bVar1 * 2);
      lVar15 = FUN_005b4690(*(undefined8 *)(param_1 + 0x28),(uint)local_22 + (uint)bVar1 * 3);
      lVar16 = FUN_005b4690(*(undefined8 *)(param_1 + 0x58),local_22);
      sVar7 = (**(code **)(**(longlong **)(param_1 + 0x28) + 0x60))(*(longlong **)(param_1 + 0x28));
      local_1e = (ushort)bVar4;
      if (local_1e <= (ushort)(sVar7 - (ushort)bVar4)) {
        sVar7 = ((sVar7 - (ushort)bVar4) - local_1e) + 1;
        do {
          uVar8 = local_1e * 3 + (ushort)param_2;
          uVar5 = FUN_0040c470((double)(((uint)*(byte *)(lVar9 + (int)((uint)uVar8 - (uint)bVar3)) +
                                         (uint)*(byte *)(lVar9 + (ulonglong)
                                                                 ((uint)uVar8 + (uint)bVar3)) +
                                         (uint)*(byte *)(lVar10 + (int)((uint)uVar8 - (uint)bVar4))
                                         + (uint)*(byte *)(lVar10 + (ulonglong)
                                                                    ((uint)uVar8 + (uint)bVar4)) +
                                         (uint)*(byte *)(lVar15 + (int)((uint)uVar8 - (uint)bVar3))
                                         + (uint)*(byte *)(lVar15 + (ulonglong)
                                                                    ((uint)uVar8 + (uint)bVar3)) +
                                         (uint)*(byte *)(lVar14 + (int)((uint)uVar8 - (uint)bVar4))
                                        + (uint)*(byte *)(lVar14 + (ulonglong)
                                                                   ((uint)uVar8 + (uint)bVar4))) *
                                        0xb + ((uint)*(byte *)(lVar9 + (int)((uint)uVar8 -
                                                                            (uint)bVar2)) +
                                               (uint)*(byte *)(lVar9 + (ulonglong)
                                                                       ((uint)uVar8 + (uint)bVar2))
                                               + (uint)*(byte *)(lVar11 + (int)((uint)uVar8 -
                                                                               (uint)bVar2)) +
                                               (uint)*(byte *)(lVar11 + (ulonglong)
                                                                        ((uint)uVar8 + (uint)bVar2))
                                               + (uint)*(byte *)(lVar15 + (int)((uint)uVar8 -
                                                                               (uint)bVar2)) +
                                               (uint)*(byte *)(lVar15 + (ulonglong)
                                                                        ((uint)uVar8 + (uint)bVar2))
                                               + (uint)*(byte *)(lVar13 + (int)((uint)uVar8 -
                                                                               (uint)bVar2)) +
                                              (uint)*(byte *)(lVar13 + (ulonglong)
                                                                       ((uint)uVar8 + (uint)bVar2)))
                                              * 0x18 +
                                        ((uint)*(byte *)(lVar9 + (ulonglong)uVar8) +
                                         (uint)*(byte *)(lVar15 + (ulonglong)uVar8) +
                                         (uint)*(byte *)(lVar12 + (int)((uint)uVar8 - (uint)bVar4))
                                        + (uint)*(byte *)(lVar12 + (ulonglong)
                                                                   ((uint)uVar8 + (uint)bVar4))) *
                                        0x1d + ((uint)*(byte *)(lVar10 + (int)((uint)uVar8 -
                                                                              (uint)bVar3)) +
                                                (uint)*(byte *)(lVar10 + (ulonglong)
                                                                         ((uint)uVar8 + (uint)bVar3)
                                                               ) +
                                                (uint)*(byte *)(lVar14 + (int)((uint)uVar8 -
                                                                              (uint)bVar3)) +
                                               (uint)*(byte *)(lVar14 + (ulonglong)
                                                                        ((uint)uVar8 + (uint)bVar3))
                                               ) * 0x2a +
                                        ((uint)*(byte *)(lVar10 + (int)((uint)uVar8 - (uint)bVar2))
                                         + (uint)*(byte *)(lVar10 + (ulonglong)
                                                                    ((uint)uVar8 + (uint)bVar2)) +
                                         (uint)*(byte *)(lVar11 + (int)((uint)uVar8 - (uint)bVar3))
                                         + (uint)*(byte *)(lVar11 + (ulonglong)
                                                                    ((uint)uVar8 + (uint)bVar3)) +
                                         (uint)*(byte *)(lVar13 + (int)((uint)uVar8 - (uint)bVar3))
                                         + (uint)*(byte *)(lVar13 + (ulonglong)
                                                                    ((uint)uVar8 + (uint)bVar3)) +
                                         (uint)*(byte *)(lVar14 + (int)((uint)uVar8 - (uint)bVar2))
                                        + (uint)*(byte *)(lVar14 + (ulonglong)
                                                                   ((uint)uVar8 + (uint)bVar2))) *
                                        0x5a + ((uint)*(byte *)(lVar10 + (ulonglong)uVar8) +
                                                (uint)*(byte *)(lVar14 + (ulonglong)uVar8) +
                                                (uint)*(byte *)(lVar12 + (int)((uint)uVar8 -
                                                                              (uint)bVar3)) +
                                               (uint)*(byte *)(lVar12 + (ulonglong)
                                                                        ((uint)uVar8 + (uint)bVar3))
                                               ) * 0x6d +
                                        ((uint)*(byte *)(lVar11 + (int)((uint)uVar8 - (uint)bVar2))
                                         + (uint)*(byte *)(lVar11 + (ulonglong)
                                                                    ((uint)uVar8 + (uint)bVar2)) +
                                         (uint)*(byte *)(lVar13 + (int)((uint)uVar8 - (uint)bVar2))
                                        + (uint)*(byte *)(lVar13 + (ulonglong)
                                                                   ((uint)uVar8 + (uint)bVar2))) *
                                        0xc3 + ((uint)*(byte *)(lVar11 + (ulonglong)uVar8) +
                                                (uint)*(byte *)(lVar13 + (ulonglong)uVar8) +
                                                (uint)*(byte *)(lVar12 + (int)((uint)uVar8 -
                                                                              (uint)bVar2)) +
                                               (uint)*(byte *)(lVar12 + (ulonglong)
                                                                        ((uint)uVar8 + (uint)bVar2))
                                               ) * 0xed +
                                       (uint)*(byte *)(lVar12 + (ulonglong)uVar8) * 0x120) /
                               _DAT_0085eb70);
          *(undefined1 *)(lVar16 + (ulonglong)uVar8) = uVar5;
          local_1e = local_1e + 1;
          sVar7 = sVar7 + -1;
        } while (sVar7 != 0);
      }
      local_22 = local_22 + 1;
      sVar6 = sVar6 + -1;
    } while (sVar6 != 0);
  }
  return;
}

/* ==================================================
 * Function: FUN_0085fe50
 * Address:  0085fe50
 * Namespace: Global
 * ================================================== */

void FUN_0085fe50(longlong *param_1,byte param_2)

{
  short sVar1;
  short sVar2;
  int iVar3;
  longlong *plVar4;
  longlong lVar5;
  longlong lVar6;
  ushort local_1e;
  short local_1c;
  ushort local_1a;
  
  plVar4 = (longlong *)FUN_005b31e0(PTR_PTR_005a1410,1);
  (**(code **)(*plVar4 + 0x10))(plVar4,param_1);
  iVar3 = (**(code **)(*param_1 + 0x60))(param_1);
  (**(code **)(*param_1 + 0x88))(param_1,iVar3 * 2);
  FUN_008638e0(param_1,0);
  sVar1 = (**(code **)(*param_1 + 0x48))();
  local_1c = 0;
  do {
    lVar5 = FUN_005b4690(plVar4,local_1c);
    lVar6 = FUN_005b4690(param_1);
    sVar2 = (**(code **)(*plVar4 + 0x60))();
    local_1a = 0;
    sVar2 = sVar2 * 3 + -2;
    do {
      local_1e = (ushort)*(byte *)(lVar5 + (ulonglong)local_1a) / (ushort)param_2;
      FUN_00409900(&local_1e,lVar6 + (ulonglong)((uint)local_1a * 2),2);
      local_1a = local_1a + 1;
      sVar2 = sVar2 + -1;
    } while (sVar2 != 0);
    local_1c = local_1c + 1;
    sVar1 = sVar1 + -1;
  } while (sVar1 != 0);
  FUN_0040f6e0(plVar4);
  return;
}

/* ==================================================
 * Function: FUN_008638e0
 * Address:  008638e0
 * Namespace: Global
 * ================================================== */

void FUN_008638e0(longlong *param_1,undefined4 param_2)

{
  undefined4 uVar1;
  undefined4 uVar2;
  longlong lVar3;
  longlong *plVar4;
  undefined1 local_28 [16];
  
  lVar3 = FUN_005b4450(param_1);
  FUN_005a8450(*(undefined8 *)(lVar3 + 0x80),0);
  lVar3 = FUN_005b4450(param_1);
  FUN_005a8250(*(undefined8 *)(lVar3 + 0x80),param_2);
  plVar4 = (longlong *)FUN_005b4450(param_1);
  uVar1 = (**(code **)(*param_1 + 0x60))(param_1);
  uVar2 = (**(code **)(*param_1 + 0x48))(param_1);
  FUN_004f28f0(local_28,0,0,uVar1,uVar2);
  (**(code **)(*plVar4 + 0xa8))(plVar4,local_28);
  return;
}

/* ==================================================
 * Function: FUN_00863980
 * Address:  00863980
 * Namespace: Global
 * ================================================== */

void FUN_00863980(longlong *param_1,undefined8 param_2)

{
  int iVar1;
  int iVar2;
  char cVar3;
  undefined4 uVar4;
  int iVar5;
  longlong *plVar6;
  longlong lVar7;
  longlong lVar8;
  longlong lVar9;
  longlong *plVar10;
  uint uVar11;
  uint uVar12;
  int iVar13;
  short local_42;
  int local_28;
  int local_24;
  int local_1c;
  
  plVar6 = (longlong *)FUN_005b31e0(PTR_PTR_005a1410,1);
  uVar4 = FUN_005b45d0(param_1);
  FUN_005b6270(plVar6,uVar4);
  cVar3 = FUN_005b45d0(param_1);
  if (cVar3 == '\x06') {
    local_42 = 3;
  }
  else {
    local_42 = 1;
  }
  iVar5 = (**(code **)(*param_1 + 0x60))(param_1);
  uVar11 = (iVar5 + 1) - (iVar5 + 1 >> 0x1f) >> 1;
  iVar5 = (**(code **)(*param_1 + 0x48))(param_1);
  uVar12 = (iVar5 + 1) - (iVar5 + 1 >> 0x1f) >> 1;
  (**(code **)(*plVar6 + 0x88))(plVar6,(short)uVar11);
  (**(code **)(*plVar6 + 0x70))(plVar6,(short)uVar12);
  if (local_42 == 3) {
    local_28 = 0;
    if (-1 < (int)((uVar12 & 0xffff) - 2)) {
      iVar5 = (uVar12 & 0xffff) - 1;
      do {
        lVar7 = FUN_005b4690(param_1,local_28 * 2);
        lVar8 = FUN_005b4690(param_1,local_28 * 2 + 1);
        lVar9 = FUN_005b4690(plVar6,local_28);
        local_1c = 0;
        if (-1 < (int)((uVar11 & 0xffff) - 2)) {
          iVar13 = (uVar11 & 0xffff) - 1;
          do {
            iVar1 = local_1c * 3;
            iVar2 = local_1c * 6;
            *(char *)(lVar9 + iVar1) =
                 (char)((uint)*(byte *)(lVar7 + iVar2) + (uint)*(byte *)(lVar7 + (iVar2 + 3)) +
                        (uint)*(byte *)(lVar8 + iVar2) + (uint)*(byte *)(lVar8 + (iVar2 + 3)) + 2 >>
                       2);
            *(char *)(lVar9 + (iVar1 + 1)) =
                 (char)((uint)*(byte *)(lVar7 + (iVar2 + 1)) + (uint)*(byte *)(lVar7 + (iVar2 + 4))
                        + (uint)*(byte *)(lVar8 + (iVar2 + 1)) +
                        (uint)*(byte *)(lVar8 + (iVar2 + 4)) + 2 >> 2);
            *(char *)(lVar9 + (iVar1 + 2)) =
                 (char)((uint)*(byte *)(lVar7 + (iVar2 + 2)) + (uint)*(byte *)(lVar7 + (iVar2 + 5))
                        + (uint)*(byte *)(lVar8 + (iVar2 + 2)) +
                        (uint)*(byte *)(lVar8 + (iVar2 + 5)) + 2 >> 2);
            local_1c = local_1c + 1;
            iVar13 = iVar13 + -1;
          } while (iVar13 != 0);
        }
        local_28 = local_28 + 1;
        iVar5 = iVar5 + -1;
      } while (iVar5 != 0);
    }
  }
  else {
    local_28 = 0;
    if (-1 < (int)((uVar12 & 0xffff) - 2)) {
      iVar5 = (uVar12 & 0xffff) - 1;
      do {
        lVar7 = FUN_005b4690(param_1,local_28 * 2);
        lVar8 = FUN_005b4690(param_1,local_28 * 2 + 1);
        lVar9 = FUN_005b4690(plVar6,local_28);
        local_24 = 0;
        if (-1 < (int)((uVar11 & 0xffff) - 2)) {
          iVar13 = (uVar11 & 0xffff) - 1;
          do {
            iVar1 = local_24 * 2;
            *(char *)(lVar9 + local_24) =
                 (char)((uint)*(byte *)(lVar7 + iVar1) + (uint)*(byte *)(lVar7 + (iVar1 + 1)) +
                        (uint)*(byte *)(lVar8 + iVar1) + (uint)*(byte *)(lVar8 + (iVar1 + 1)) + 2 >>
                       2);
            local_24 = local_24 + 1;
            iVar13 = iVar13 + -1;
          } while (iVar13 != 0);
        }
        local_28 = local_28 + 1;
        iVar5 = iVar5 + -1;
      } while (iVar5 != 0);
    }
  }
  FUN_0040f6e0(param_2);
  plVar10 = (longlong *)FUN_005b31e0(PTR_PTR_005a1410,1);
  (**(code **)(*plVar10 + 0x10))(plVar10,plVar6);
  FUN_0040f6e0(plVar6);
  return;
}

/* ==================================================
 * Function: FUN_008644a0
 * Address:  008644a0
 * Namespace: Global
 * ================================================== */

void FUN_008644a0(longlong *param_1,longlong *param_2)

{
  ushort uVar1;
  short sVar2;
  short sVar3;
  undefined4 uVar4;
  longlong lVar5;
  longlong lVar6;
  undefined2 local_2e;
  undefined2 local_2c;
  
  FUN_005b6270(param_2,3);
  uVar4 = (**(code **)(*param_1 + 0x60))(param_1);
  (**(code **)(*param_2 + 0x88))(param_2,uVar4);
  uVar4 = (**(code **)(*param_1 + 0x48))(param_1);
  (**(code **)(*param_2 + 0x70))(param_2,uVar4);
  sVar2 = (**(code **)(*param_2 + 0x48))();
  local_2e = 0;
  do {
    lVar5 = FUN_005b4690(param_1,local_2e);
    lVar6 = FUN_005b4690(param_2,local_2e);
    sVar3 = (**(code **)(*param_2 + 0x60))();
    local_2c = 0;
    do {
      uVar1 = local_2c * 3;
      *(char *)(lVar6 + (ulonglong)local_2c) =
           (char)((ulonglong)
                  ((uint)*(byte *)(lVar5 + (ulonglong)uVar1) * 0x36 +
                   (uint)*(byte *)(lVar5 + (ulonglong)(uVar1 + 1)) * 0x78 +
                   (uint)*(byte *)(lVar5 + (ulonglong)(uVar1 + 2)) * 0x51 + 0x7f) / 0xff);
      local_2c = local_2c + 1;
      sVar3 = sVar3 + -1;
    } while (sVar3 != 0);
    local_2e = local_2e + 1;
    sVar2 = sVar2 + -1;
  } while (sVar2 != 0);
  return;
}
