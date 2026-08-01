/*
 Additional decompiled functions that are adjacent to stacking.
 This is Ghidra-style output, not original source code.
*/

/* ==================================================
 * Function: FUN_008c08c0
 * Address:  008c08c0
 * Namespace: Global
 * ================================================== */

void FUN_008c08c0(longlong param_1)

{
  longlong *plVar1;
  undefined8 local_40;
  undefined8 local_38;
  longlong local_30 [2];
  short local_1a;
  
  local_38 = 0;
  local_40 = 0;
  local_30[0] = 0;
  local_1a = 0;
  while( true ) {
    plVar1 = *(longlong **)(*(longlong *)(param_1 + 0x770) + 0x4e0);
    (**(code **)(*plVar1 + 0x18))(plVar1,local_30,local_1a);
    if (*(short *)(local_30[0] + 2) == 0x58) break;
    local_1a = local_1a + 1;
  }
  plVar1 = *(longlong **)(*(longlong *)(param_1 + 0x770) + 0x4e0);
  (**(code **)(*plVar1 + 0x18))(plVar1,&local_40,local_1a);
  FUN_00414400(&local_38,local_40,5,0xf9);
  FUN_008bde10(param_1,local_38,DAT_00968f70);
  (**(code **)(*DAT_00968f80 + 0x10))(DAT_00968f80,DAT_00968f70);
  (**(code **)(*DAT_00968f88 + 0x10))(DAT_00968f88,DAT_00968f70);
  (**(code **)(*DAT_00968f90 + 0x10))(DAT_00968f90,DAT_00968f70);
  (**(code **)(*DAT_00968f38 + 0x10))(DAT_00968f38,DAT_00968f70);
  FUN_008638e0(DAT_00968f38,0);
  (**(code **)(*DAT_00968f40 + 0x10))(DAT_00968f40,DAT_00968f38);
  (**(code **)(*DAT_00968f48 + 0x10))(DAT_00968f48,DAT_00968f38);
  DAT_00968ef0 = (longlong *)FUN_005b31e0(PTR_PTR_005a1410,1);
  (**(code **)(*DAT_00968ef0 + 0x10))(DAT_00968ef0,DAT_00968f38);
  plVar1 = (longlong *)
           FUN_005ae7d0(*(undefined8 *)
                         (*(longlong *)(*(longlong *)PTR_DAT_00952838 + 0x738) + 0x338));
  (**(code **)(*plVar1 + 0x10))(plVar1,DAT_00968f70);
  FUN_005f05c0(*(undefined8 *)(*(longlong *)PTR_DAT_00952838 + 0x738),1);
  FUN_005f05c0(*(undefined8 *)(*(longlong *)PTR_DAT_00952838 + 0x780),1);
  FUN_00712250(*(undefined8 *)(*(longlong *)PTR_DAT_00952838 + 0x768),1);
  DAT_00968e98 = DAT_00968e90;
  FUN_008a1a40(*(undefined8 *)PTR_DAT_00952838);
  FUN_00412a30(&local_40,3);
  return;
}

/* ==================================================
 * Function: FUN_008c0fc0
 * Address:  008c0fc0
 * Namespace: Global
 * ================================================== */

void FUN_008c0fc0(void)

{
  *PTR_DAT_009539c0 = 0;
  if (*(char *)(*(longlong *)(DAT_00968e60 + 0x990) + 0x80) != '\0') {
    *PTR_DAT_009539c0 = *PTR_DAT_009539c0 | 1;
  }
  if (*(char *)(*(longlong *)(DAT_00968e60 + 0x9a8) + 0x80) != '\0') {
    *PTR_DAT_009539c0 = *PTR_DAT_009539c0 | 2;
  }
  *(undefined4 *)(PTR_DAT_009539c0 + 1) = 0;
  *(undefined4 *)(PTR_DAT_009539c0 + 5) = 0;
  *(undefined8 *)(PTR_DAT_009539c0 + 9) = 0;
  *(undefined8 *)(PTR_DAT_009539c0 + 0x11) = 0;
  return;
}

/* ==================================================
 * Function: FUN_008c24b0
 * Address:  008c24b0
 * Namespace: Global
 * ================================================== */

void FUN_008c24b0(longlong param_1)

{
  longlong *plVar1;
  undefined8 local_50;
  undefined8 local_48;
  undefined8 local_40;
  int local_34;
  longlong local_30;
  int local_24;
  longlong local_20;
  
  local_50 = 0;
  local_48 = 0;
  local_40 = 0;
  FUN_0043ad90(&local_40,((uint)DAT_00968e88 - (uint)DAT_00968e86) + 1);
  FUN_00413070(param_1 + 0xf8,local_40);
  local_20 = *(longlong *)(param_1 + 0xf8);
  local_24 = 0;
  if (local_20 != 0) {
    local_24 = *(int *)(local_20 + -4);
  }
  if (local_24 < 2) {
    FUN_004141b0(param_1 + 0xf8,&DAT_008c2718,*(undefined8 *)(param_1 + 0xf8));
  }
  local_30 = *(longlong *)(param_1 + 0xf8);
  local_34 = 0;
  if (local_30 != 0) {
    local_34 = *(int *)(local_30 + -4);
  }
  if (local_34 < 3) {
    FUN_004141b0(param_1 + 0xf8,&DAT_008c2718,*(undefined8 *)(param_1 + 0xf8));
  }
  if (DAT_00968e72 < 0x32) {
    plVar1 = (longlong *)
             FUN_005ae7d0(*(undefined8 *)
                           (*(longlong *)(*(longlong *)PTR_DAT_00952838 + 0x738) + 0x338));
    (**(code **)(*plVar1 + 0x10))(plVar1,DAT_00968f88);
    FUN_004142e0(&local_48,4,*(undefined8 *)PTR_DAT_00953ce8,L"step_",
                 *(undefined8 *)(param_1 + 0xf8),L".bmp");
    (**(code **)(*DAT_00968f88 + 0xb8))(DAT_00968f88,local_48);
  }
  else {
    plVar1 = (longlong *)
             FUN_005ae7d0(*(undefined8 *)
                           (*(longlong *)(*(longlong *)PTR_DAT_00952838 + 0x738) + 0x338));
    (**(code **)(*plVar1 + 0x10))(plVar1,DAT_00968ee8);
    FUN_004142e0(&local_50,4,*(undefined8 *)PTR_DAT_00953ce8,L"step_",
                 *(undefined8 *)(param_1 + 0xf8),L".bmp");
    (**(code **)(*DAT_00968ee8 + 0xb8))(DAT_00968ee8,local_50);
  }
  FUN_00412a30(&local_50,3);
  return;
}

/* ==================================================
 * Function: FUN_008c2750
 * Address:  008c2750
 * Namespace: Global
 * ================================================== */

void FUN_008c2750(void)

{
  uint uVar1;
  undefined8 uVar2;
  
  uVar1 = (**(code **)(*DAT_00968f70 + 0x60))(DAT_00968f70);
  if ((uVar1 == DAT_00968ff8) &&
     (uVar1 = (**(code **)(*DAT_00968f70 + 0x48))(DAT_00968f70), uVar1 == DAT_00968ffa)) {
    return;
  }
  uVar2 = FUN_004467c0(PTR_PTR_0042eeb8,1,L"All images must have the same dimensions!");
  FUN_00411bf0(uVar2);
  return;
}

/* ==================================================
 * Function: FUN_008c26f0
 * Address:  008c26f0
 * Namespace: Global
 * ================================================== */

void FUN_008c26f0(undefined8 param_1,longlong param_2)

{
  FUN_00412a30(param_2 + 0x38,3);
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
 * Function: FUN_00865340
 * Address:  00865340
 * Namespace: Global
 * ================================================== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

longlong * FUN_00865340(longlong *param_1,longlong *param_2,char param_3)

{
  longlong *plVar1;
  int iVar2;
  int iVar3;
  undefined4 uVar4;
  undefined4 uVar5;
  undefined1 auStack_c8 [32];
  longlong *local_a8;
  longlong *local_a0;
  byte local_91;
  longlong *local_90;
  longlong *local_88;
  double local_78;
  double local_70;
  double local_68;
  double local_60;
  longlong *local_28;
  undefined1 local_19;
  
  local_28 = (longlong *)FUN_005b31e0(PTR_PTR_005a1410,1);
  (**(code **)(*local_28 + 0x10))(local_28,param_1);
  if (param_3 == '\0') {
    iVar2 = (**(code **)(*param_1 + 0x60))(param_1);
    iVar3 = (**(code **)(*param_1 + 0x48))(param_1);
    if (iVar2 * iVar3 < 0x7e9000) {
      local_91 = 1;
      goto LAB_008653d9;
    }
  }
  local_91 = 2;
LAB_008653d9:
  FUN_008644a0(param_1,local_28);
  if (1 < local_91) {
    FUN_00863980(local_28,local_28);
  }
  local_90 = (longlong *)FUN_005b31e0(PTR_PTR_005a1410,1);
  (**(code **)(*local_90 + 0x10))(local_90,param_2);
  FUN_008644a0(param_2,local_90);
  if (1 < local_91) {
    FUN_00863980(local_90,local_90);
  }
  local_19 = (DAT_00962260 & 2) == 2;
  local_70 = (double)DAT_00962261;
  local_78 = (double)DAT_00962265;
  local_68 = DAT_00962269;
  local_60 = DAT_00962271;
  FUN_00864bb0(auStack_c8,local_28,local_90,1);
  FUN_00864bb0(auStack_c8,local_28,local_90,2);
  if (((DAT_00962260 & 1) == 1) &&
     (_DAT_008656a0 < (double)((ulonglong)local_68 & (ulonglong)DAT_008656c0))) {
    FUN_008631e0(param_2,local_68 + _DAT_008656a8,local_68 + _DAT_008656a8);
  }
  if ((DAT_00962260 & 2) == 2) {
    iVar2 = (**(code **)(*param_2 + 0x60))(param_2);
    iVar3 = (**(code **)(*param_2 + 0x48))(param_2);
    FUN_00862ca0(param_2,iVar2 / 2,iVar3 / 2,local_60);
  }
  uVar4 = FUN_0040c470(local_70 * (double)local_91);
  uVar5 = FUN_0040c470(local_78 * (double)local_91);
  FUN_00863730(param_2,uVar4,uVar5);
  DAT_00962261 = FUN_0040c470(local_70 + (local_70 - (double)DAT_00962261) * _DAT_008656b0);
  DAT_00962265 = FUN_0040c470(local_78 + (local_78 - (double)DAT_00962265) * _DAT_008656b0);
  plVar1 = local_28;
  DAT_00962269 = local_68 * _DAT_008656b0;
  DAT_00962271 = local_60 + (local_60 - DAT_00962271) * _DAT_008656b8;
  local_a0 = local_28;
  local_28 = (longlong *)0x0;
  local_88 = param_2;
  FUN_0040f6e0(plVar1);
  plVar1 = local_90;
  local_a8 = local_90;
  local_90 = (longlong *)0x0;
  FUN_0040f6e0(plVar1);
  return local_88;
}

/* ==================================================
 * Function: FUN_008bde10
 * Address:  008bde10
 * Namespace: Global
 * ================================================== */

void FUN_008bde10(undefined8 param_1,undefined8 param_2,undefined8 param_3)

{
  undefined8 local_res10;
  undefined8 local_res18;
  undefined1 auStack_168 [40];
  undefined8 local_140;
  undefined8 local_138;
  undefined8 local_130;
  undefined8 local_128;
  undefined8 local_120;
  undefined8 local_118;
  undefined8 local_110;
  undefined8 local_108;
  undefined8 local_100;
  undefined8 local_f8;
  undefined8 local_f0 [2];
  bool local_d9;
  int local_d8;
  int local_d4;
  undefined8 local_d0;
  bool local_c1;
  int local_c0;
  int local_bc;
  undefined8 local_b8;
  bool local_a9;
  int local_a8;
  int local_a4;
  undefined8 local_a0;
  bool local_91;
  int local_90;
  int local_8c;
  undefined8 local_88;
  bool local_79;
  int local_78;
  int local_74;
  undefined8 local_70;
  bool local_61;
  int local_60;
  int local_5c;
  undefined8 local_58;
  bool local_49;
  int local_48;
  int local_44;
  undefined8 local_40;
  bool local_31;
  int local_30;
  int local_2c;
  undefined8 local_28;
  int local_20;
  int local_1c;
  undefined8 local_18;
  longlong local_10;
  
  local_140 = 0;
  local_138 = 0;
  local_130 = 0;
  local_128 = 0;
  local_120 = 0;
  local_118 = 0;
  local_110 = 0;
  local_108 = 0;
  local_100 = 0;
  local_f8 = 0;
  local_f0[0] = 0;
  local_10 = 0;
  local_res10 = param_2;
  local_res18 = param_3;
  FUN_00412b20(param_2);
  FUN_0043c2b0(local_f0,local_res10);
  FUN_004141b0(&local_10,*(undefined8 *)PTR_DAT_00953ce8,local_f0[0]);
  FUN_00439c80(&local_f8,local_10);
  local_18 = local_f8;
  local_20 = FUN_00414610(L".bmp",local_f8,1);
  local_1c = 0;
  if (local_10 != 0) {
    local_1c = *(int *)(local_10 + -4);
  }
  if (local_20 == local_1c + -3) {
    local_31 = true;
  }
  else {
    FUN_00439c80(&local_100,local_10);
    local_28 = local_100;
    local_30 = FUN_00414610(L".jpg",local_100,1);
    local_2c = 0;
    if (local_10 != 0) {
      local_2c = *(int *)(local_10 + -4);
    }
    local_31 = local_30 == local_2c + -3;
  }
  if (local_31 == false) {
    FUN_00439c80(&local_108,local_10);
    local_40 = local_108;
    local_48 = FUN_00414610(L".jpeg",local_108,1);
    local_44 = 0;
    if (local_10 != 0) {
      local_44 = *(int *)(local_10 + -4);
    }
    local_49 = local_48 == local_44 + -4;
  }
  else {
    local_49 = true;
  }
  if (local_49 == false) {
    FUN_00439c80(&local_110,local_10);
    local_58 = local_110;
    local_60 = FUN_00414610(L".png",local_110,1);
    local_5c = 0;
    if (local_10 != 0) {
      local_5c = *(int *)(local_10 + -4);
    }
    local_61 = local_60 == local_5c + -3;
  }
  else {
    local_61 = true;
  }
  if (local_61 == false) {
    FUN_00439c80(&local_118,local_10);
    local_70 = local_118;
    local_78 = FUN_00414610(L".gif",local_118,1);
    local_74 = 0;
    if (local_10 != 0) {
      local_74 = *(int *)(local_10 + -4);
    }
    local_79 = local_78 == local_74 + -3;
  }
  else {
    local_79 = true;
  }
  if (local_79 == false) {
    FUN_00439c80(&local_120,local_10);
    local_88 = local_120;
    local_90 = FUN_00414610(L".tif",local_120,1);
    local_8c = 0;
    if (local_10 != 0) {
      local_8c = *(int *)(local_10 + -4);
    }
    local_91 = local_8c + -4 <= local_90;
  }
  else {
    local_91 = true;
  }
  if (local_91 == false) {
    FUN_00439c80(&local_128,local_10);
    local_a0 = local_128;
    local_a8 = FUN_00414610(L".dng",local_128,1);
    local_a4 = 0;
    if (local_10 != 0) {
      local_a4 = *(int *)(local_10 + -4);
    }
    local_a9 = local_a8 == local_a4 + -3;
  }
  else {
    local_a9 = true;
  }
  if (local_a9 == false) {
    FUN_00439c80(&local_130,local_10);
    local_b8 = local_130;
    local_c0 = FUN_00414610(L".cr2",local_130,1);
    local_bc = 0;
    if (local_10 != 0) {
      local_bc = *(int *)(local_10 + -4);
    }
    local_c1 = local_c0 == local_bc + -3;
  }
  else {
    local_c1 = true;
  }
  if (local_c1 == false) {
    FUN_00439c80(&local_138,local_10);
    local_d0 = local_138;
    local_d8 = FUN_00414610(L".nef",local_138,1);
    local_d4 = 0;
    if (local_10 != 0) {
      local_d4 = *(int *)(local_10 + -4);
    }
    local_d9 = local_d8 == local_d4 + -3;
  }
  else {
    local_d9 = true;
  }
  if (local_d9 != false) {
    FUN_008bdcb0(auStack_168);
  }
  DAT_00968e6e = (**(code **)(*DAT_00968f70 + 0x60))(DAT_00968f70);
  DAT_00968e70 = (**(code **)(*DAT_00968f70 + 0x48))(DAT_00968f70);
  FUN_0043c2b0(&local_140,local_10);
  FUN_00412fe0(&DAT_00968ec0,local_140);
  FUN_00412a30(&local_140,0xb);
  FUN_00412950(&local_10);
  FUN_00412950(&local_res10);
  return;
}

/* ==================================================
 * Function: FUN_008cca70
 * Address:  008cca70
 * Namespace: Global
 * ================================================== */

void FUN_008cca70(longlong param_1)

{
  undefined8 uVar1;
  int iVar2;
  undefined4 uVar3;
  longlong *plVar4;
  undefined1 auStack_c8 [40];
  undefined8 local_a0;
  undefined8 local_98;
  undefined8 local_90;
  undefined8 local_88;
  undefined8 local_80;
  undefined8 local_78;
  undefined8 local_70 [2];
  longlong *local_60;
  undefined8 local_58;
  undefined8 local_50;
  undefined8 local_48;
  undefined8 local_40;
  int local_38;
  int local_34;
  longlong *local_30;
  undefined8 local_28;
  int local_1c;
  
  local_a0 = 0;
  local_98 = 0;
  local_90 = 0;
  local_88 = 0;
  local_80 = 0;
  local_78 = 0;
  local_70[0] = 0;
  local_28 = 0;
  local_30 = (longlong *)FUN_005b31e0(PTR_PTR_005a1410,1);
  FUN_008c0fc0();
  plVar4 = *(longlong **)(*(longlong *)(param_1 + 0x770) + 0x4e0);
  local_1c = (**(code **)(*plVar4 + 0x28))(plVar4);
  local_1c = local_1c + -1;
  local_38 = 0;
  do {
    plVar4 = *(longlong **)(*(longlong *)(param_1 + 0x770) + 0x4e0);
    (**(code **)(*plVar4 + 0x18))(plVar4,local_70,local_1c);
    local_40 = local_70[0];
    iVar2 = FUN_00414610(&DAT_008cd02c,local_70[0],1);
    if (iVar2 == 1) {
      local_38 = local_38 + 1;
    }
    local_1c = local_1c + -1;
  } while (local_38 < (int)(uint)(DAT_00968e88 >> 1));
  local_34 = local_1c;
  plVar4 = *(longlong **)(*(longlong *)(param_1 + 0x770) + 0x4e0);
  (**(code **)(*plVar4 + 0x18))(plVar4,&local_78,local_1c);
  FUN_00414400(&local_28,local_78,5,0xf9);
  uVar1 = DAT_00968f70;
  local_48 = DAT_00968f70;
  DAT_00968f70 = 0;
  FUN_0040f6e0(uVar1);
  DAT_00968f70 = FUN_005b31e0(PTR_PTR_005a1410,1);
  FUN_008bde10(param_1,local_28,DAT_00968f70);
  (**(code **)(*local_30 + 0x10))(local_30,DAT_00968f70);
  FUN_004141b0(&local_80,&DAT_008cd040,local_28);
  FUN_008bfdb0(param_1,local_30,local_80);
  FUN_004141b0(&local_88,L"[X] ",DAT_00968ec8);
  plVar4 = *(longlong **)(*(longlong *)(param_1 + 0x770) + 0x4e0);
  (**(code **)(*plVar4 + 0x40))(plVar4,local_1c,local_88);
  FUN_005f07e0(*(undefined8 *)PTR_DAT_00952838,L"PROGRAM: Alignment in progress...");
  FUN_00412fe0(&DAT_00969018,L"Alignment");
  DAT_00969014 = DAT_00968e88;
  FUN_00899ac0(*(undefined8 *)PTR_DAT_00952260,DAT_00968e60);
  uVar3 = (**(code **)(*local_30 + 0x60))(local_30);
  FUN_005ef360(*(undefined8 *)(*(longlong *)PTR_DAT_00952838 + 0x738),uVar3);
  uVar3 = (**(code **)(*local_30 + 0x48))(local_30);
  FUN_005ef3c0(*(undefined8 *)(*(longlong *)PTR_DAT_00952838 + 0x738),uVar3);
  plVar4 = (longlong *)
           FUN_005ae7d0(*(undefined8 *)
                         (*(longlong *)(*(longlong *)PTR_DAT_00952838 + 0x738) + 0x338));
  (**(code **)(*plVar4 + 0x10))(plVar4,local_30);
  FUN_005f10d0(*(undefined8 *)(*(longlong *)PTR_DAT_00952838 + 0x738));
  FUN_005f0ba0(*(undefined8 *)(*(longlong *)PTR_DAT_00952838 + 0x738));
  DAT_00968e98 = DAT_00968e90;
  FUN_008a1a40(*(undefined8 *)PTR_DAT_00952838);
  while (0 < local_1c) {
    local_1c = local_1c + -1;
    if (-1 < local_1c) {
      plVar4 = *(longlong **)(*(longlong *)(param_1 + 0x770) + 0x4e0);
      (**(code **)(*plVar4 + 0x18))(plVar4,&local_90,local_1c);
      local_50 = local_90;
      iVar2 = FUN_00414610(&DAT_008cd02c,local_90,1);
      if ((iVar2 == 1) && (DAT_00968fb7 == '\0')) {
        FUN_008cc880(auStack_c8);
      }
    }
  }
  plVar4 = *(longlong **)(*(longlong *)(param_1 + 0x770) + 0x4e0);
  (**(code **)(*plVar4 + 0x18))(plVar4,&local_98,local_34);
  FUN_00414400(&local_28,local_98,5,0xf9);
  FUN_008bde10(param_1,local_28,DAT_00968f70);
  (**(code **)(*local_30 + 0x10))(local_30,DAT_00968f70);
  FUN_008c0fc0();
  local_1c = local_34;
  while( true ) {
    local_1c = local_1c + 1;
    plVar4 = *(longlong **)(*(longlong *)(param_1 + 0x770) + 0x4e0);
    iVar2 = (**(code **)(*plVar4 + 0x28))(plVar4);
    if (iVar2 <= local_1c) break;
    plVar4 = *(longlong **)(*(longlong *)(param_1 + 0x770) + 0x4e0);
    (**(code **)(*plVar4 + 0x18))(plVar4,&local_a0,local_1c);
    local_58 = local_a0;
    iVar2 = FUN_00414610(&DAT_008cd02c,local_a0,1);
    if ((iVar2 == 1) && (DAT_00968fb7 == '\0')) {
      FUN_008cc880(auStack_c8);
    }
  }
  FUN_00899b50(*(undefined8 *)PTR_DAT_00952260,DAT_00968e60);
  FUN_005f07e0(*(undefined8 *)PTR_DAT_00952838,L"Alignment done.");
  FUN_008bd480(param_1);
  plVar4 = local_30;
  local_60 = local_30;
  local_30 = (longlong *)0x0;
  FUN_0040f6e0(plVar4);
  FUN_00412a30(&local_a0,7);
  FUN_00412950(&local_28);
  return;
}

/* ==================================================
 * Function: FUN_0085f730
 * Address:  0085f730
 * Namespace: Global
 * ================================================== */

void FUN_0085f730(longlong *param_1,undefined8 param_2)

{
  short sVar1;
  short sVar2;
  ushort uVar3;
  uint uVar4;
  longlong lVar5;
  longlong lVar6;
  uint uVar7;
  uint uVar8;
  uint uVar9;
  short local_2e;
  short local_2a;
  
  sVar1 = (**(code **)(*param_1 + 0x48))();
  local_2e = 0;
  do {
    lVar5 = FUN_005b4690(param_1,local_2e);
    lVar6 = FUN_005b4690(param_2,local_2e);
    sVar2 = (**(code **)(*param_1 + 0x60))();
    local_2a = 0;
    do {
      uVar3 = local_2a * 3 + 2;
      *(char *)(lVar5 + (ulonglong)uVar3) = -1 - *(char *)(lVar5 + (ulonglong)uVar3);
      uVar4 = (uint)*(byte *)(lVar6 + (int)(uVar3 - 2)) - (uint)*(byte *)(lVar6 + (int)(uVar3 - 1));
      uVar7 = (int)uVar4 >> 0x1f;
      uVar8 = (uint)*(byte *)(lVar6 + (ulonglong)uVar3) - (uint)*(byte *)(lVar6 + (int)(uVar3 - 1));
      uVar9 = (int)uVar8 >> 0x1f;
      if (0x28 < (int)(((uVar4 ^ uVar7) - uVar7) + ((uVar8 ^ uVar9) - uVar9))) {
        FUN_00409900(&DAT_00962279 + (ulonglong)*(byte *)(lVar5 + (ulonglong)uVar3) * 3,
                     lVar6 + (int)(uVar3 - 2),3);
      }
      local_2a = local_2a + 1;
      sVar2 = sVar2 + -1;
    } while (sVar2 != 0);
    local_2e = local_2e + 1;
    sVar1 = sVar1 + -1;
  } while (sVar1 != 0);
  return;
}

/* ==================================================
 * Function: FUN_0085f8c0
 * Address:  0085f8c0
 * Namespace: Global
 * ================================================== */

void FUN_0085f8c0(longlong *param_1)

{
  longlong *plVar1;
  short sVar2;
  short sVar3;
  undefined8 local_50;
  longlong *local_48;
  short local_36;
  ushort local_34;
  short local_32;
  longlong local_30;
  longlong local_28;
  longlong *local_20;
  
  local_50 = 0;
  local_20 = (longlong *)FUN_005b31e0(PTR_PTR_005a1410,1);
  (**(code **)(*local_20 + 0x10))(local_20,param_1);
  sVar2 = (**(code **)(*param_1 + 0x48))();
  local_36 = 0;
  do {
    local_28 = FUN_005b4690(param_1,local_36);
    local_30 = FUN_005b4690(local_20,local_36);
    sVar3 = (**(code **)(*param_1 + 0x60))();
    local_32 = 0;
    do {
      local_34 = local_32 * 3 + 2;
      *(byte *)(local_30 + (ulonglong)local_34) = *(byte *)(local_28 + (ulonglong)local_34) ^ 0xff;
      *(byte *)(local_30 + (int)(local_34 - 1)) = *(byte *)(local_28 + (ulonglong)local_34) ^ 0xff;
      *(byte *)(local_30 + (int)(local_34 - 2)) = *(byte *)(local_28 + (ulonglong)local_34) ^ 0xff;
      local_32 = local_32 + 1;
      sVar3 = sVar3 + -1;
    } while (sVar3 != 0);
    local_36 = local_36 + 1;
    sVar2 = sVar2 + -1;
  } while (sVar2 != 0);
  FUN_004141b0(&local_50,DAT_00963988,L"depthmap_grey.bmp");
  (**(code **)(*local_20 + 0xb8))(local_20,local_50);
  plVar1 = local_20;
  local_48 = local_20;
  local_20 = (longlong *)0x0;
  FUN_0040f6e0(plVar1);
  FUN_00412950(&local_50);
  return;
}

/* ==================================================
 * Function: FUN_008c6120
 * Address:  008c6120
 * Namespace: Global
 * ================================================== */

void FUN_008c6120(longlong param_1)

{
  longlong *plVar1;
  undefined1 uVar2;
  int iVar3;
  undefined1 auStack_88 [40];
  undefined8 local_60;
  undefined8 local_58;
  undefined8 local_50;
  undefined8 local_48;
  undefined8 local_40;
  undefined8 local_38;
  short local_2a;
  undefined8 local_28 [3];
  
  local_60 = 0;
  local_58 = 0;
  local_50 = 0;
  local_48 = 0;
  local_40 = 0;
  local_28[0] = 0;
  if (1 < DAT_00968e88) {
    DAT_00968fb7 = 0;
    DAT_00968fb3 = (**(code **)(**(longlong **)(param_1 + 0xa80) + 0x2d8))
                             (*(longlong **)(param_1 + 0xa80));
    FUN_005f0770(*(undefined8 *)(param_1 + 0xb88),&local_40);
    DAT_00968e72 = FUN_0043b040(local_40);
    FUN_005f0770(*(undefined8 *)(param_1 + 0xbc8),&local_48);
    uVar2 = FUN_0043b040(local_48);
    *PTR_DAT_00952538 = uVar2;
    FUN_008cc6a0(param_1,DAT_00968e90);
    if ((*(char *)(*(longlong *)(param_1 + 0x978) + 0x80) == '\0') && (DAT_00968e82 == 0)) {
      FUN_00412950(&DAT_00968ea8);
    }
    else {
      local_2a = 0;
      while( true ) {
        plVar1 = *(longlong **)(*(longlong *)(param_1 + 0x770) + 0x4e0);
        (**(code **)(*plVar1 + 0x18))(plVar1,&local_50,local_2a);
        local_38 = local_50;
        iVar3 = FUN_00414610(&DAT_008c6454,local_50,1);
        if (iVar3 == 1) break;
        local_2a = local_2a + 1;
      }
      plVar1 = *(longlong **)(*(longlong *)(param_1 + 0x770) + 0x4e0);
      (**(code **)(*plVar1 + 0x18))(plVar1,&local_58,local_2a);
      FUN_00414400(local_28,local_58,5,0xf9);
      FUN_0043c040(&local_60,local_28[0],0);
      FUN_004141b0(&DAT_00968ea8,&DAT_008c6468,local_60);
    }
    if (DAT_00968fb3 == '\0') {
      FUN_008c4c90(auStack_88);
    }
    else {
      FUN_008c5f70(auStack_88);
    }
    FUN_00712110(*(undefined8 *)(*(longlong *)PTR_DAT_00952838 + 0x750),L"[&Flip view=] Result");
    FUN_00712250(*(undefined8 *)(*(longlong *)PTR_DAT_00952838 + 0x750),1);
    FUN_00712250(*(undefined8 *)(param_1 + 0x768),1);
    FUN_00712250(*(undefined8 *)(param_1 + 0x7f0),1);
    FUN_00712250(*(undefined8 *)(param_1 + 0x778),1);
    (**(code **)(**(longlong **)(param_1 + 0x770) + 0x2e0))(*(longlong **)(param_1 + 0x770),0);
    DAT_00968e84 = DAT_00968e88;
    DAT_00968e79 = 1;
    DAT_00968e7a = 1;
    FUN_00899b50(*(undefined8 *)PTR_DAT_00952260,DAT_00968e60);
    FUN_00712250(*(undefined8 *)(*(longlong *)PTR_DAT_00952838 + 0x778),1);
  }
  FUN_00412a30(&local_60,3);
  FUN_00412a30(&local_48,2);
  FUN_00412950(local_28);
  return;
}

/* ==================================================
 * Function: FUN_008c6d20
 * Address:  008c6d20
 * Namespace: Global
 * ================================================== */

void FUN_008c6d20(longlong param_1)

{
  longlong *plVar1;
  undefined8 local_40;
  undefined8 local_38;
  longlong local_30 [2];
  ushort local_1c;
  short local_1a;
  
  local_38 = 0;
  local_40 = 0;
  local_30[0] = 0;
  FUN_0073c610(*(undefined8 *)PTR_DAT_00952838);
  FUN_00412fe0(&DAT_00969018,L"Averaging");
  DAT_00969014 = DAT_00968e88;
  FUN_00899ac0(*(undefined8 *)PTR_DAT_00952260);
  DAT_00968fb7 = '\0';
  local_1a = 0;
  local_1c = 0;
  if (DAT_00968e88 < 0x100) {
    DAT_00969012 = '\x01';
  }
  else {
    DAT_00969012 = (char)((ulonglong)DAT_00968e88 / 0xff) + '\x01';
  }
  for (; (DAT_00968fb7 == '\0' && (local_1c < DAT_00968e88)); local_1c = local_1c + 1) {
    while( true ) {
      plVar1 = *(longlong **)(*(longlong *)(param_1 + 0x770) + 0x4e0);
      (**(code **)(*plVar1 + 0x18))(plVar1,local_30,local_1a);
      if (*(short *)(local_30[0] + 2) == 0x58) break;
      local_1a = local_1a + 1;
    }
    plVar1 = *(longlong **)(*(longlong *)(param_1 + 0x770) + 0x4e0);
    (**(code **)(*plVar1 + 0x18))(plVar1,&local_40,local_1a);
    FUN_00414400(&local_38,local_40,5,0xf9);
    FUN_008bde10(param_1,local_38,DAT_00968f70);
    FUN_0085ffb0(DAT_00968f70,DAT_00968f60,DAT_00968f68,DAT_00968f50,local_1c,DAT_00969012);
    local_1a = local_1a + 1;
  }
  FUN_0085fcc0(DAT_00968f50,local_1c,DAT_00969012);
  plVar1 = (longlong *)
           FUN_005ae7d0(*(undefined8 *)
                         (*(longlong *)(*(longlong *)PTR_DAT_00952838 + 0x738) + 0x338));
  (**(code **)(*plVar1 + 0x10))(plVar1,DAT_00968f50);
  FUN_00743f80(*(undefined8 *)PTR_DAT_009533c0);
  FUN_00899b50(*(undefined8 *)PTR_DAT_00952260,DAT_00968e60);
  FUN_00412a30(&local_40,3);
  return;
}

/* ==================================================
 * Function: FUN_008c6f90
 * Address:  008c6f90
 * Namespace: Global
 * ================================================== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

void FUN_008c6f90(longlong param_1)

{
  ushort uVar1;
  char cVar2;
  int iVar3;
  uint uVar4;
  uint uVar5;
  uint uVar6;
  longlong *plVar7;
  undefined8 uVar8;
  short sVar9;
  short sVar10;
  double dVar11;
  undefined8 local_100;
  undefined8 local_f8;
  ulonglong local_f0;
  undefined8 local_e8;
  undefined8 local_e0;
  undefined8 local_d8;
  undefined8 local_d0;
  undefined8 local_c8;
  longlong local_c0;
  undefined8 local_b8;
  undefined8 local_b0;
  undefined8 local_a8;
  undefined8 local_a0 [2];
  int local_8c;
  undefined8 local_88;
  undefined8 local_80;
  undefined8 local_78;
  longlong *local_68;
  undefined8 local_60;
  uint local_54;
  longlong local_50;
  longlong local_48;
  longlong local_40;
  int local_34;
  int local_30;
  int local_2c;
  int local_28;
  byte local_24;
  byte local_23;
  byte local_22;
  byte local_21;
  short local_20;
  ushort local_1e;
  ushort local_1c;
  ushort local_1a;
  
  local_100 = 0;
  local_f8 = 0;
  local_f0 = 0;
  local_e8 = 0;
  local_d8 = 0;
  local_e0 = 0;
  local_c8 = 0;
  local_d0 = 0;
  local_c0 = 0;
  local_b0 = 0;
  local_b8 = 0;
  local_a8 = 0;
  local_a0[0] = 0;
  local_50 = 0;
  local_60 = 0;
  local_2c = 0;
  local_30 = 0;
  local_34 = 0;
  if (DAT_00968e88 != 0) {
    FUN_00412fe0(&DAT_00969018,L"Background correction");
    DAT_00969014 = DAT_00968e88;
    FUN_00899ac0(*(undefined8 *)PTR_DAT_00952260,DAT_00968e60);
    FUN_005f0770(*(undefined8 *)(param_1 + 0x830),local_a0);
    FUN_0085fba0(&local_60,local_a0[0]);
    dVar11 = (double)FUN_00440120(local_60,PTR_DAT_009537e8);
    local_54 = FUN_0040c470(dVar11 * _DAT_008c82a0);
    local_78 = *(undefined8 *)(*(longlong *)(param_1 + 0x860) + 0x78);
    iVar3 = FUN_00414610(L"Original",local_78,1);
    if ((0 < iVar3) && (iVar3 = FUN_004143b0(DAT_00968eb0,L"asis"), iVar3 == 0)) {
      FUN_00412fe0(&DAT_00968eb0,L".bmp");
    }
    FUN_0073c610(*(undefined8 *)PTR_DAT_00952838);
    local_1a = 0;
    local_1c = 0;
    while( true ) {
      plVar7 = *(longlong **)(*(longlong *)(param_1 + 0x770) + 0x4e0);
      (**(code **)(*plVar7 + 0x18))(plVar7,&local_a8,(uint)local_1c + (uint)local_1a);
      local_80 = local_a8;
      iVar3 = FUN_00414610(&DAT_008c838c,local_a8,1);
      if (iVar3 != 0) break;
      local_1a = local_1a + 1;
    }
    plVar7 = *(longlong **)(*(longlong *)(param_1 + 0x770) + 0x4e0);
    (**(code **)(*plVar7 + 0x18))(plVar7,&local_b8,(uint)local_1c + (uint)local_1a);
    FUN_00414400(&local_b0,local_b8,5,0xf9);
    FUN_008bde10(param_1,local_b0,DAT_00968f70);
    local_68 = (longlong *)FUN_005b31e0(PTR_PTR_005a1410,1);
    (**(code **)(*local_68 + 0x10))(local_68,DAT_00968f70);
    if ((DAT_00968e76 == '\x05') || (DAT_00968e76 == '\n')) {
      if (DAT_00968e76 == '\n') {
        uVar4 = *(uint *)(*(longlong *)(param_1 + 0x858) + 200) >> 0x10;
        uVar5 = *(uint *)(*(longlong *)(param_1 + 0x858) + 200) >> 8 & 0xff;
        uVar6 = *(uint *)(*(longlong *)(param_1 + 0x858) + 200) & 0xff;
        local_21 = (byte)(uVar4 * 0x1c + uVar5 * 0x96 + uVar6 * 0x4d >> 8);
        local_34 = (int)((local_21 - uVar4) * 0xff) / (int)(uint)local_21;
        local_30 = (int)((local_21 - uVar5) * 0xff) / (int)(uint)local_21;
        local_2c = (int)((local_21 - uVar6) * 0xff) / (int)(uint)local_21;
      }
      else {
        local_54 = (local_54 ^ (int)local_54 >> 0x1f) - ((int)local_54 >> 0x1f);
        local_24 = (byte)((uint)*(undefined4 *)(*(longlong *)(param_1 + 0x858) + 200) >> 0x10);
        local_23 = (byte)((uint)*(undefined4 *)(*(longlong *)(param_1 + 0x858) + 200) >> 8);
        local_22 = *(byte *)(*(longlong *)(param_1 + 0x858) + 200);
        local_20 = 0;
        sVar10 = DAT_00968e70;
        do {
          local_40 = FUN_005b4690(local_68,local_20);
          for (local_1e = 0; (uint)local_1e < (uint)DAT_00968e6e * 3; local_1e = local_1e + 3) {
            if (*(byte *)(local_40 + (ulonglong)local_1e) < local_24) {
              *(byte *)(local_40 + (ulonglong)local_1e) =
                   local_24 - *(char *)(local_40 + (ulonglong)local_1e) & 0xfe;
            }
            else {
              *(byte *)(local_40 + (ulonglong)local_1e) =
                   *(char *)(local_40 + (ulonglong)local_1e) - local_24 | 1;
            }
            uVar1 = local_1e + 1;
            if (*(byte *)(local_40 + (ulonglong)uVar1) < local_23) {
              *(byte *)(local_40 + (ulonglong)uVar1) =
                   local_23 - *(char *)(local_40 + (ulonglong)uVar1) & 0xfe;
            }
            else {
              *(byte *)(local_40 + (ulonglong)uVar1) =
                   *(char *)(local_40 + (ulonglong)uVar1) - local_23 | 1;
            }
            uVar1 = local_1e + 2;
            if (*(byte *)(local_40 + (ulonglong)uVar1) < local_22) {
              *(byte *)(local_40 + (ulonglong)uVar1) =
                   local_22 - *(char *)(local_40 + (ulonglong)uVar1) & 0xfe;
            }
            else {
              *(byte *)(local_40 + (ulonglong)uVar1) =
                   *(char *)(local_40 + (ulonglong)uVar1) - local_22 | 1;
            }
          }
          local_20 = local_20 + 1;
          sVar10 = sVar10 + -1;
        } while (sVar10 != 0);
      }
    }
    else {
      local_20 = 0;
      sVar10 = DAT_00968e70;
      do {
        local_40 = FUN_005b4690(local_68,local_20);
        local_1e = 0;
        uVar4 = (int)local_54 >> 0x1f;
        if ((int)local_54 < 1) {
          for (; (uint)local_1e < (uint)DAT_00968e6e * 3; local_1e = local_1e + 1) {
            *(byte *)(local_40 + (ulonglong)local_1e) =
                 (byte)((uint)*(byte *)(local_40 + (ulonglong)local_1e) *
                        ((local_54 ^ uVar4) - uVar4) >> 8) | 1;
          }
        }
        else {
          for (; (uint)local_1e < (uint)DAT_00968e6e * 3; local_1e = local_1e + 1) {
            *(byte *)(local_40 + (ulonglong)local_1e) =
                 (byte)((uint)*(byte *)(local_40 + (ulonglong)local_1e) *
                        ((local_54 ^ uVar4) - uVar4) >> 8) & 0xfe;
          }
        }
        local_20 = local_20 + 1;
        sVar10 = sVar10 + -1;
      } while (sVar10 != 0);
    }
    local_1c = (ushort)(DAT_00968e76 != '\n');
    if (local_1c < DAT_00968e88) {
      do {
        while (plVar7 = *(longlong **)(*(longlong *)(param_1 + 0x770) + 0x4e0),
              (**(code **)(*plVar7 + 0x18))(plVar7,&local_c0,(uint)local_1c + (uint)local_1a),
              *(short *)(local_c0 + 2) != 0x58) {
          local_1a = local_1a + 1;
        }
        plVar7 = *(longlong **)(*(longlong *)(param_1 + 0x770) + 0x4e0);
        (**(code **)(*plVar7 + 0x18))(plVar7,&local_d0,(uint)local_1c + (uint)local_1a);
        FUN_00414400(&local_c8,local_d0,5,0xf9);
        FUN_008bde10(param_1,local_c8,DAT_00968f70);
        plVar7 = (longlong *)
                 FUN_005ae7d0(*(undefined8 *)
                               (*(longlong *)(*(longlong *)PTR_DAT_00952838 + 0x738) + 0x338));
        (**(code **)(*plVar7 + 0x10))(plVar7,DAT_00968f70);
        if ((DAT_00968e76 == '\x05') || (DAT_00968e76 == '\n')) {
          if (DAT_00968e76 == '\n') {
            local_20 = 0;
            sVar10 = DAT_00968e70;
            do {
              uVar8 = FUN_005ae7d0(*(undefined8 *)
                                    (*(longlong *)(*(longlong *)PTR_DAT_00952838 + 0x738) + 0x338));
              local_48 = FUN_005b4690(uVar8,local_20);
              for (local_1e = 0; (int)(uint)local_1e < (int)((DAT_00968e6e - 1) * 3);
                  local_1e = local_1e + 3) {
                local_21 = (byte)((uint)*(byte *)(local_48 + (ulonglong)local_1e) * 0x1c +
                                  (uint)*(byte *)(local_48 + (ulonglong)(local_1e + 1)) * 0x96 +
                                  (uint)*(byte *)(local_48 + (ulonglong)(local_1e + 2)) * 0x4d >> 8)
                ;
                iVar3 = (int)(local_34 * (uint)local_21) / 0xff;
                if ((int)((uint)*(byte *)(local_48 + (ulonglong)local_1e) + iVar3) < 0xff) {
                  if ((int)((uint)*(byte *)(local_48 + (ulonglong)local_1e) + iVar3) < 1) {
                    *(undefined1 *)(local_48 + (ulonglong)local_1e) = 0;
                  }
                  else {
                    local_28._0_1_ = (char)iVar3;
                    *(char *)(local_48 + (ulonglong)local_1e) =
                         *(char *)(local_48 + (ulonglong)local_1e) + (char)local_28;
                  }
                }
                else {
                  *(undefined1 *)(local_48 + (ulonglong)local_1e) = 0xff;
                }
                uVar1 = local_1e + 1;
                iVar3 = (int)(local_30 * (uint)local_21) / 0xff;
                if ((int)((uint)*(byte *)(local_48 + (ulonglong)uVar1) + iVar3) < 0xff) {
                  if ((int)((uint)*(byte *)(local_48 + (ulonglong)uVar1) + iVar3) < 1) {
                    *(undefined1 *)(local_48 + (ulonglong)uVar1) = 0;
                  }
                  else {
                    local_28._0_1_ = (char)iVar3;
                    *(char *)(local_48 + (ulonglong)uVar1) =
                         *(char *)(local_48 + (ulonglong)uVar1) + (char)local_28;
                  }
                }
                else {
                  *(undefined1 *)(local_48 + (ulonglong)uVar1) = 0xff;
                }
                uVar1 = local_1e + 2;
                local_28 = (int)(local_2c * (uint)local_21) / 0xff;
                if ((int)((uint)*(byte *)(local_48 + (ulonglong)uVar1) + local_28) < 0xff) {
                  if ((int)((uint)*(byte *)(local_48 + (ulonglong)uVar1) + local_28) < 1) {
                    *(undefined1 *)(local_48 + (ulonglong)uVar1) = 0;
                  }
                  else {
                    *(char *)(local_48 + (ulonglong)uVar1) =
                         *(char *)(local_48 + (ulonglong)uVar1) + (char)local_28;
                  }
                }
                else {
                  *(undefined1 *)(local_48 + (ulonglong)uVar1) = 0xff;
                }
              }
              local_20 = local_20 + 1;
              sVar10 = sVar10 + -1;
            } while (sVar10 != 0);
          }
          else {
            local_20 = 0;
            sVar10 = DAT_00968e70;
            do {
              local_40 = FUN_005b4690(local_68,local_20);
              uVar8 = FUN_005ae7d0(*(undefined8 *)
                                    (*(longlong *)(*(longlong *)PTR_DAT_00952838 + 0x738) + 0x338));
              local_48 = FUN_005b4690(uVar8,local_20);
              sVar9 = DAT_00968e6e * 3;
              local_1e = 0;
              do {
                if ((*(byte *)(local_40 + (ulonglong)local_1e) & 1) == 0) {
                  iVar3 = *(byte *)(local_40 + (ulonglong)local_1e) * local_54;
                  if (iVar3 < 0) {
                    iVar3 = iVar3 + 0xff;
                  }
                  if ((int)((iVar3 >> 8) + (uint)*(byte *)(local_48 + (ulonglong)local_1e)) < 0x100)
                  {
                    iVar3 = *(byte *)(local_40 + (ulonglong)local_1e) * local_54;
                    if (iVar3 < 0) {
                      iVar3 = iVar3 + 0xff;
                    }
                    *(char *)(local_48 + (ulonglong)local_1e) =
                         *(char *)(local_48 + (ulonglong)local_1e) + (char)((uint)iVar3 >> 8);
                  }
                  else {
                    *(undefined1 *)(local_48 + (ulonglong)local_1e) = 0xff;
                  }
                }
                else {
                  iVar3 = *(byte *)(local_40 + (ulonglong)local_1e) * local_54;
                  if (iVar3 < 0) {
                    iVar3 = iVar3 + 0xff;
                  }
                  if ((int)(uint)*(byte *)(local_48 + (ulonglong)local_1e) < iVar3 >> 8) {
                    *(undefined1 *)(local_48 + (ulonglong)local_1e) = 0;
                  }
                  else {
                    iVar3 = *(byte *)(local_40 + (ulonglong)local_1e) * local_54;
                    if (iVar3 < 0) {
                      iVar3 = iVar3 + 0xff;
                    }
                    *(char *)(local_48 + (ulonglong)local_1e) =
                         *(char *)(local_48 + (ulonglong)local_1e) - (char)((uint)iVar3 >> 8);
                  }
                }
                local_1e = local_1e + 1;
                sVar9 = sVar9 + -1;
              } while (sVar9 != 0);
              local_20 = local_20 + 1;
              sVar10 = sVar10 + -1;
            } while (sVar10 != 0);
          }
        }
        else {
          local_20 = 0;
          sVar10 = DAT_00968e70;
          do {
            local_40 = FUN_005b4690(local_68,local_20);
            uVar8 = FUN_005ae7d0(*(undefined8 *)
                                  (*(longlong *)(*(longlong *)PTR_DAT_00952838 + 0x738) + 0x338));
            local_48 = FUN_005b4690(uVar8,local_20);
            sVar9 = DAT_00968e6e * 3;
            local_1e = 0;
            do {
              if ((*(byte *)(local_40 + (ulonglong)local_1e) & 1) == 0) {
                if ((uint)*(byte *)(local_48 + (ulonglong)local_1e) +
                    (uint)*(byte *)(local_40 + (ulonglong)local_1e) < 0x100) {
                  *(char *)(local_48 + (ulonglong)local_1e) =
                       *(char *)(local_48 + (ulonglong)local_1e) +
                       *(char *)(local_40 + (ulonglong)local_1e);
                }
                else {
                  *(undefined1 *)(local_48 + (ulonglong)local_1e) = 0xff;
                }
              }
              else if ((int)((uint)*(byte *)(local_48 + (ulonglong)local_1e) -
                            (uint)*(byte *)(local_40 + (ulonglong)local_1e)) < 0) {
                *(undefined1 *)(local_48 + (ulonglong)local_1e) = 0;
              }
              else {
                *(char *)(local_48 + (ulonglong)local_1e) =
                     *(char *)(local_48 + (ulonglong)local_1e) -
                     *(char *)(local_40 + (ulonglong)local_1e);
              }
              local_1e = local_1e + 1;
              sVar9 = sVar9 + -1;
            } while (sVar9 != 0);
            local_20 = local_20 + 1;
            sVar10 = sVar10 + -1;
          } while (sVar10 != 0);
        }
        plVar7 = *(longlong **)(*(longlong *)(param_1 + 0x770) + 0x4e0);
        (**(code **)(*plVar7 + 0x18))(plVar7,&local_e0,(uint)local_1c + (uint)local_1a);
        FUN_00414400(&local_d8,local_e0,5,0xfa);
        FUN_004141b0(&local_50,DAT_00968ea0,local_d8);
        local_88 = *(undefined8 *)(*(longlong *)(param_1 + 0x860) + 0x78);
        iVar3 = FUN_00414610(L"Original",local_88,1);
        if ((0 < iVar3) && (iVar3 = FUN_004143b0(DAT_00968eb0,L"asis"), iVar3 == 0)) {
          FUN_00412fe0(&DAT_00968eb0,L".jpg");
        }
        local_8c = 0;
        if (local_50 != 0) {
          local_8c = *(int *)(local_50 + -4);
        }
        FUN_00414400(&local_e8,local_50,1,local_8c + -4);
        FUN_004141b0(&local_50,local_e8,DAT_00968eb0);
        uVar8 = FUN_005ae7d0(*(undefined8 *)
                              (*(longlong *)(*(longlong *)PTR_DAT_00952838 + 0x738) + 0x338));
        FUN_008bfdb0(param_1,uVar8,local_50);
        FUN_004141b0(&local_f0,L"[_] ",local_50);
        cVar2 = FUN_008bda70(param_1,local_f0);
        if (cVar2 != '\0') {
          if (DAT_00968e76 == '\n') {
            FUN_004141b0(&local_f8,L"[_] ",local_50);
            plVar7 = *(longlong **)(*(longlong *)(param_1 + 0x770) + 0x4e0);
            (**(code **)(*plVar7 + 200))(plVar7,local_1c,local_f8);
          }
          else {
            FUN_004141b0(&local_100,L"[_] ",local_50);
            plVar7 = *(longlong **)(*(longlong *)(param_1 + 0x770) + 0x4e0);
            (**(code **)(*plVar7 + 200))(plVar7,local_1c - 1,local_100);
          }
          local_1a = local_1a + 1;
        }
        local_1c = local_1c + 1;
      } while (local_1c < DAT_00968e88);
    }
    FUN_00743f80(*(undefined8 *)PTR_DAT_009533c0);
    FUN_0073c610(*(undefined8 *)PTR_DAT_00952838);
    FUN_005f10c0(*(undefined8 *)(*(longlong *)PTR_DAT_00952838 + 0x780));
    FUN_005f0ba0(*(undefined8 *)(*(longlong *)PTR_DAT_00952838 + 0x738));
    FUN_00712250(*(undefined8 *)(*(longlong *)PTR_DAT_00952838 + 0x768),1);
    FUN_00712250(*(undefined8 *)(*(longlong *)PTR_DAT_00952838 + 0x750),0);
    FUN_005f0ba0(*(undefined8 *)PTR_DAT_00952838);
    FUN_0040f6e0(local_68);
    FUN_00899b50(*(undefined8 *)PTR_DAT_00952260,DAT_00968e60);
  }
  FUN_00412a30(&local_100,0xc);
  FUN_00412950(local_a0);
  FUN_00412950(&local_60);
  FUN_00412950(&local_50);
  return;
}

/* ==================================================
 * Function: FUN_008c83d0
 * Address:  008c83d0
 * Namespace: Global
 * ================================================== */

void FUN_008c83d0(longlong param_1)

{
  char cVar1;
  uint uVar2;
  uint uVar3;
  int iVar4;
  longlong *plVar5;
  ushort uVar6;
  uint uVar7;
  ushort uVar8;
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
  longlong local_88;
  undefined8 local_80;
  undefined8 local_78;
  longlong local_70;
  undefined8 local_68;
  byte local_5c;
  byte local_5b;
  byte local_5a;
  byte local_59;
  undefined1 local_58;
  byte local_57;
  byte local_56;
  byte local_55;
  byte local_54;
  byte local_53 [3];
  longlong local_50;
  longlong local_48;
  longlong local_40;
  longlong local_38;
  longlong local_30;
  longlong local_28;
  ushort local_1e;
  ushort local_1c;
  ushort local_1a;
  
  local_e8 = 0;
  local_e0 = 0;
  local_c8 = 0;
  local_d0 = 0;
  local_d8 = 0;
  local_c0 = 0;
  local_b8 = 0;
  local_a0 = 0;
  local_a8 = 0;
  local_b0 = 0;
  local_90 = 0;
  local_98 = 0;
  local_88 = 0;
  local_78 = 0;
  local_80 = 0;
  local_70 = 0;
  DAT_00968e76 = 2;
  local_54 = '\0';
  while (plVar5 = *(longlong **)(*(longlong *)(param_1 + 0x770) + 0x4e0),
        (**(code **)(*plVar5 + 0x18))(plVar5,&local_70,local_54), *(short *)(local_70 + 2) != 0x58)
  {
    local_54 = local_54 + '\x01';
  }
  plVar5 = *(longlong **)(*(longlong *)(param_1 + 0x770) + 0x4e0);
  (**(code **)(*plVar5 + 0x18))(plVar5,&local_80,local_54);
  FUN_00414400(&local_78,local_80,5,0xf9);
  FUN_008bde10(param_1,local_78,DAT_00968f70);
  local_53[2] = *(byte *)(*(longlong *)(*(longlong *)PTR_DAT_00953648 + 0x7a8) + 200);
  local_53[1] = (byte)((uint)*(undefined4 *)
                              (*(longlong *)(*(longlong *)PTR_DAT_00953648 + 0x7a8) + 200) >> 8);
  local_53[0] = (byte)((uint)*(undefined4 *)
                              (*(longlong *)(*(longlong *)PTR_DAT_00953648 + 0x7a8) + 200) >> 0x10);
  FUN_0073c610(*(undefined8 *)PTR_DAT_00952838);
  FUN_005f0ba0(*(undefined8 *)PTR_DAT_00952838);
  FUN_005f07e0(*(undefined8 *)PTR_DAT_00952838,L"PROGRAM: Stacking in progress...");
  (**(code **)(*DAT_00968f98 + 0x10))(DAT_00968f98,DAT_00968f70);
  (**(code **)(*DAT_00968fa0 + 0x10))(DAT_00968fa0,DAT_00968f98);
  FUN_008638e0(DAT_00968fa0,0xffff00);
  (**(code **)(*DAT_00968f78 + 0x10))(DAT_00968f78,DAT_00968fa0);
  if (local_53[0] < local_53[1]) {
    if (local_53[2] < local_53[1]) {
      local_59 = 1;
      if (local_53[0] < local_53[2]) {
        local_5a = 2;
        local_5b = 0;
      }
      else {
        local_5a = 0;
        local_5b = 2;
      }
    }
    else {
      local_5a = 1;
      if (local_53[0] < local_53[2]) {
        local_59 = 2;
        local_5b = 0;
      }
      else {
        local_59 = 0;
        local_5b = 2;
      }
    }
  }
  else if (local_53[0] < local_53[2]) {
    local_59 = 2;
    local_5a = 0;
    local_5b = 1;
  }
  else {
    local_59 = 0;
    if (local_53[1] < local_53[2]) {
      local_5a = 2;
      local_5b = 1;
    }
    else {
      local_5a = 1;
      local_5b = 2;
    }
  }
  local_55 = local_53[local_59] - local_53[local_5a];
  local_56 = local_53[local_59] - local_53[local_5b];
  local_54 = 0;
  local_1a = 0;
  if (DAT_00968e88 != 0) {
    do {
      while (plVar5 = *(longlong **)(*(longlong *)(param_1 + 0x770) + 0x4e0),
            (**(code **)(*plVar5 + 0x18))(plVar5,&local_88,(uint)local_1a + (uint)local_54),
            *(short *)(local_88 + 2) != 0x58) {
        local_54 = local_54 + 1;
      }
      plVar5 = *(longlong **)(*(longlong *)(param_1 + 0x770) + 0x4e0);
      (**(code **)(*plVar5 + 0x18))(plVar5,&local_98,(uint)local_1a + (uint)local_54);
      FUN_00414400(&local_90,local_98,5,0xf9);
      FUN_008bde10(param_1,local_90,DAT_00968f70);
      local_5c = FUN_0040c470((double)((uint)local_1a * 0x100 - (uint)local_1a) /
                              (double)DAT_00968e88);
      for (local_1e = 1; (int)(uint)local_1e < (int)(DAT_00968e70 - 1); local_1e = local_1e + 1) {
        local_48 = FUN_005b4690(DAT_00968f70,local_1e - 1);
        local_38 = FUN_005b4690(DAT_00968f70,local_1e);
        local_40 = FUN_005b4690(DAT_00968f70,local_1e + 1);
        local_28 = FUN_005b4690(DAT_00968f98,local_1e);
        local_30 = FUN_005b4690(DAT_00968f78,local_1e);
        local_50 = FUN_005b4690(DAT_00968fa0,local_1e);
        for (local_1c = 3; (uint)local_1c < (uint)DAT_00968e6e * 3; local_1c = local_1c + 3) {
          uVar2 = (uint)*(byte *)(local_48 + (ulonglong)((uint)local_1c + (uint)local_59)) +
                  (uint)*(byte *)(local_38 + (int)((uint)local_1c + (uint)local_59 + -3)) +
                  (uint)*(byte *)(local_38 + (ulonglong)((uint)local_1c + (uint)local_59)) * 4 +
                  (uint)*(byte *)(local_38 + (ulonglong)((uint)local_1c + (uint)local_59 + 3)) +
                  (uint)*(byte *)(local_40 + (ulonglong)((uint)local_1c + (uint)local_59)) +
                  (uint)local_53[local_59] * -8;
          uVar3 = (int)uVar2 >> 0x1f;
          uVar2 = ((uVar2 ^ uVar3) - uVar3) + 4 >> 3;
          local_57 = (byte)uVar2;
          uVar3 = (uint)*(byte *)(local_48 + (ulonglong)((uint)local_1c + (uint)local_5a)) +
                  (uint)*(byte *)(local_38 + (int)((uint)local_1c + (uint)local_5a + -3)) +
                  (uint)*(byte *)(local_38 + (ulonglong)((uint)local_1c + (uint)local_5a)) * 4 +
                  (uint)*(byte *)(local_38 + (ulonglong)((uint)local_1c + (uint)local_5a + 3)) +
                  (uint)*(byte *)(local_40 + (ulonglong)((uint)local_1c + (uint)local_5a)) +
                  (uint)local_53[local_5a] * -8;
          uVar7 = (int)uVar3 >> 0x1f;
          uVar3 = ((uVar3 ^ uVar7) - uVar7) + 4 >> 4;
          local_58 = (undefined1)uVar3;
          if ((uVar2 & 0xff) + (uVar3 & 0xff) <
              (uint)*(byte *)(local_50 + (ulonglong)local_1c) +
              (uint)*(byte *)(local_50 + (ulonglong)(local_1c + 1))) {
            *(byte *)(local_50 + (ulonglong)local_1c) = local_57;
            *(undefined1 *)(local_50 + (ulonglong)(local_1c + 1)) = local_58;
            *(byte *)(local_50 + (ulonglong)(local_1c + 2)) = local_5c;
            FUN_00409900(local_38 + (ulonglong)local_1c,local_28 + (ulonglong)local_1c,3);
            FUN_00409900(PTR_DAT_00952770 + (ulonglong)local_5c * 3,local_30 + (ulonglong)local_1c,3
                        );
          }
        }
      }
      local_1a = local_1a + 1;
      if (DAT_00968fb7 != '\0') {
        local_1a = DAT_00968e88;
      }
    } while (local_1a < DAT_00968e88);
  }
  cVar1 = (**(code **)(**(longlong **)(param_1 + 0x818) + 0x2d8))(*(longlong **)(param_1 + 0x818));
  if (cVar1 != '\0') {
    local_1e = 0;
    uVar8 = DAT_00968e70;
    do {
      local_38 = FUN_005b4690(DAT_00968f98,local_1e);
      local_1c = 0;
      uVar6 = DAT_00968e6e;
      do {
        local_57 = *(byte *)(local_38 + (ulonglong)((uint)local_1c * 3 + (uint)local_59));
        if ((int)((uint)local_57 - (uint)local_55) < 1) {
          *(undefined1 *)(local_38 + (ulonglong)((uint)local_1c * 3 + (uint)local_5a)) = 0;
        }
        else {
          *(byte *)(local_38 + (ulonglong)((uint)local_1c * 3 + (uint)local_5a)) =
               local_57 - local_55;
        }
        if ((int)((uint)local_57 - (uint)local_56) < 1) {
          *(undefined1 *)(local_38 + (ulonglong)((uint)local_1c * 3 + (uint)local_5b)) = 0;
        }
        else {
          *(byte *)(local_38 + (ulonglong)((uint)local_1c * 3 + (uint)local_5b)) =
               local_57 - local_56;
        }
        local_1c = local_1c + 1;
        uVar6 = uVar6 - 1;
      } while (uVar6 != 0);
      local_1e = local_1e + 1;
      uVar8 = uVar8 - 1;
    } while (uVar8 != 0);
  }
  local_68 = *(undefined8 *)(*(longlong *)(param_1 + 0x860) + 0x78);
  iVar4 = FUN_00414610(L"Original",local_68,1);
  if ((0 < iVar4) && (iVar4 = FUN_004143b0(DAT_00968eb0,L"asis"), iVar4 == 0)) {
    FUN_00412fe0(&DAT_00968eb0,L".bmp");
  }
  FUN_005f0770(*(undefined8 *)(*(longlong *)PTR_DAT_00953648 + 0x778),&local_a0);
  FUN_005f0770(*(undefined8 *)(*(longlong *)PTR_DAT_00953648 + 0x780),&local_a8);
  FUN_005f0770(*(undefined8 *)(*(longlong *)PTR_DAT_00953648 + 0x788),&local_b0);
  FUN_004142e0(&DAT_00968ec8,9,DAT_00968ea0,L"col_r",local_a0,&DAT_008c9448,local_a8,&DAT_008c945c,
               local_b0,DAT_00968ea8,DAT_00968eb0);
  FUN_008bfdb0(param_1,DAT_00968f98,DAT_00968ec8);
  FUN_004141b0(&local_b8,L"[_] ",DAT_00968ec8);
  cVar1 = FUN_008bda70(param_1,local_b8);
  if (cVar1 != '\0') {
    FUN_004141b0(&local_c0,L"[_] ",DAT_00968ec8);
    plVar5 = *(longlong **)(*(longlong *)(param_1 + 0x770) + 0x4e0);
    (**(code **)(*plVar5 + 200))(plVar5,0,local_c0);
  }
  (**(code **)(**(longlong **)(param_1 + 0x770) + 0x2e0))(*(longlong **)(param_1 + 0x770),0);
  if (DAT_00968e7f != '\0') {
    FUN_005f0770(*(undefined8 *)(*(longlong *)PTR_DAT_00953648 + 0x778),&local_c8);
    FUN_005f0770(*(undefined8 *)(*(longlong *)PTR_DAT_00953648 + 0x780),&local_d0);
    FUN_005f0770(*(undefined8 *)(*(longlong *)PTR_DAT_00953648 + 0x788),&local_d8);
    FUN_004142e0(&DAT_00968ec8,9,DAT_00968ea0,L"map_r",local_c8,&DAT_008c9448,local_d0,&DAT_008c945c
                 ,local_d8,DAT_00968ea8,DAT_00968eb0);
    FUN_008bfdb0(param_1,DAT_00968f78,DAT_00968ec8);
    FUN_004141b0(&local_e0,L"[_] ",DAT_00968ec8);
    cVar1 = FUN_008bda70(param_1,local_e0);
    if (cVar1 != '\0') {
      FUN_004141b0(&local_e8,L"[_] ",DAT_00968ec8);
      plVar5 = *(longlong **)(*(longlong *)(param_1 + 0x770) + 0x4e0);
      (**(code **)(*plVar5 + 200))(plVar5,1,local_e8);
    }
    (**(code **)(**(longlong **)(param_1 + 0x770) + 0x2e0))(*(longlong **)(param_1 + 0x770),0);
  }
  plVar5 = (longlong *)
           FUN_005ae7d0(*(undefined8 *)
                         (*(longlong *)(*(longlong *)PTR_DAT_00952838 + 0x738) + 0x338));
  (**(code **)(*plVar5 + 0x10))(plVar5,DAT_00968f98);
  FUN_0073c610(*(undefined8 *)PTR_DAT_00952838);
  FUN_005f0ba0(*(undefined8 *)(*(longlong *)PTR_DAT_00952838 + 0x738));
  FUN_00712250(*(undefined8 *)(*(longlong *)PTR_DAT_00952838 + 0x750),1);
  FUN_00712110(*(undefined8 *)(*(longlong *)PTR_DAT_00952838 + 0x750),L"[&Flip view=] Depth map");
  FUN_008a22b0(*(undefined8 *)PTR_DAT_00952838,*(undefined8 *)PTR_DAT_00952838);
  (**(code **)(*DAT_00968f58 + 0x10))(DAT_00968f58,DAT_00968f98);
  DAT_00968e79 = 1;
  DAT_00968e7a = 1;
  FUN_00712250(*(undefined8 *)(param_1 + 0x768),1);
  FUN_00712250(*(undefined8 *)(param_1 + 0x7f0),
               *(undefined1 *)(*(longlong *)(param_1 + 0x768) + 0x81));
  FUN_00712250(*(undefined8 *)(param_1 + 0x778),1);
  FUN_00899b50(*(undefined8 *)PTR_DAT_00952260,DAT_00968e60);
  FUN_00412a30(&local_e8,2);
  FUN_00412a30(&local_d8,3);
  FUN_00412a30(&local_c0,2);
  FUN_00412a30(&local_b0,3);
  FUN_00412a30(&local_98,6);
  return;
}

/* ==================================================
 * Function: FUN_008c9520
 * Address:  008c9520
 * Namespace: Global
 * ================================================== */

void FUN_008c9520(longlong param_1)

{
  longlong *plVar1;
  int iVar2;
  undefined8 local_58;
  undefined8 local_50;
  undefined8 local_48;
  undefined8 local_40;
  undefined8 local_38;
  undefined8 local_30;
  undefined8 local_28;
  short local_1a;
  
  local_48 = 0;
  local_50 = 0;
  local_58 = 0;
  local_40 = 0;
  local_38 = 0;
  local_30 = 0;
  if (DAT_00968e88 != 0) {
    if (*(char *)(*(longlong *)(param_1 + 0x978) + 0x80) == '\0') {
      FUN_00412950(&DAT_00968ea8);
    }
    else {
      local_1a = 0;
      while( true ) {
        plVar1 = *(longlong **)(*(longlong *)(param_1 + 0x770) + 0x4e0);
        (**(code **)(*plVar1 + 0x18))(plVar1,&local_30,local_1a);
        local_28 = local_30;
        iVar2 = FUN_00414610(&DAT_008c97f8,local_30,1);
        if (iVar2 == 1) break;
        local_1a = local_1a + 1;
      }
      plVar1 = *(longlong **)(*(longlong *)(param_1 + 0x770) + 0x4e0);
      (**(code **)(*plVar1 + 0x18))(plVar1,&local_38,local_1a);
      FUN_00414400(&DAT_00968ea8,local_38,5,0xf9);
      FUN_0043c040(&local_40,DAT_00968ea8,0);
      FUN_004141b0(&DAT_00968ea8,&DAT_008c980c,local_40);
    }
    DAT_00968fb7 = 0;
    FUN_00412fe0(&DAT_00969018,L"Colour stacking");
    DAT_00969014 = DAT_00968e88;
    FUN_00899ac0(*(undefined8 *)PTR_DAT_00952260,DAT_00968e60);
    FUN_008cc6a0(param_1,DAT_00968e90);
    FUN_005f10d0(*(undefined8 *)(*(longlong *)PTR_DAT_00952838 + 0x738));
    plVar1 = *(longlong **)(*(longlong *)(param_1 + 0x770) + 0x4e0);
    (**(code **)(*plVar1 + 0x18))(plVar1,&local_58,0);
    FUN_00414400(&local_50,local_58,5,0xf9);
    FUN_004141b0(&local_48,L"PROGRAM: R e s u l t  ",local_50);
    FUN_005f07e0(*(undefined8 *)PTR_DAT_00952838,local_48);
    FUN_008c83d0(param_1,DAT_00968e60);
    (**(code **)(*DAT_00968f30 + 0x88))(DAT_00968f30,DAT_00968e6e);
    (**(code **)(*DAT_00968f30 + 0x70))(DAT_00968f30,DAT_00968e70);
    (**(code **)(*DAT_00968f30 + 0x10))(DAT_00968f30,DAT_00968f98);
    FUN_00899b50(*(undefined8 *)PTR_DAT_00952260,DAT_00968e60);
    DAT_00968e84 = DAT_00968e88;
  }
  FUN_00412a30(&local_58,6);
  return;
}

/* ==================================================
 * Function: FUN_008c9cb0
 * Address:  008c9cb0
 * Namespace: Global
 * ================================================== */

void FUN_008c9cb0(longlong param_1,longlong *param_2,longlong *param_3,undefined8 param_4)

{
  int iVar1;
  int iVar2;
  undefined4 uVar3;
  longlong *plVar4;
  longlong *plVar5;
  undefined8 local_res20;
  
  local_res20 = param_4;
  FUN_00412b20(param_4);
  plVar4 = (longlong *)FUN_005b31e0(PTR_PTR_005a1410,1);
  FUN_005b6270(plVar4,6);
  iVar1 = (**(code **)(*param_2 + 0x60))(param_2);
  iVar2 = (**(code **)(*param_3 + 0x60))(param_3);
  if (iVar1 < iVar2) {
    uVar3 = (**(code **)(*param_3 + 0x60))(param_3);
    (**(code **)(*param_2 + 0x88))(param_2,uVar3);
  }
  iVar1 = (**(code **)(*param_2 + 0x60))(param_2);
  (**(code **)(*plVar4 + 0x88))(plVar4,iVar1 * 2);
  iVar1 = (**(code **)(*param_2 + 0x48))(param_2);
  iVar2 = (**(code **)(*param_3 + 0x48))(param_3);
  if (iVar1 < iVar2) {
    uVar3 = (**(code **)(*param_3 + 0x48))(param_3);
    (**(code **)(*param_2 + 0x70))(param_2,uVar3);
  }
  uVar3 = (**(code **)(*param_2 + 0x48))(param_2);
  (**(code **)(*plVar4 + 0x70))(plVar4,uVar3);
  plVar5 = (longlong *)FUN_005b4450(plVar4);
  (**(code **)(*plVar5 + 0x88))(plVar5,0,0,param_2);
  plVar5 = (longlong *)FUN_005b4450(plVar4);
  uVar3 = (**(code **)(*param_2 + 0x60))(param_2);
  (**(code **)(*plVar5 + 0x88))(plVar5,uVar3,0,param_3);
  FUN_008bfdb0(*(undefined8 *)(param_1 + 0x90),plVar4,local_res20);
  FUN_0040f6e0(plVar4);
  FUN_00412950(&local_res20);
  return;
}

/* ==================================================
 * Function: FUN_008cc6a0
 * Address:  008cc6a0
 * Namespace: Global
 * ================================================== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

void FUN_008cc6a0(undefined8 param_1,double param_2)

{
  int iVar1;
  undefined4 uVar2;
  longlong *plVar3;
  
  FUN_0073c610(*(undefined8 *)PTR_DAT_00952838);
  DAT_00968e98 = param_2;
  (**(code **)(**(longlong **)(*(longlong *)PTR_DAT_00952838 + 0x738) + 0x128))
            (*(longlong **)(*(longlong *)PTR_DAT_00952838 + 0x738),0);
  plVar3 = (longlong *)
           FUN_005ae7d0(*(undefined8 *)
                         (*(longlong *)(*(longlong *)PTR_DAT_00953178 + 0x738) + 0x338));
  iVar1 = (**(code **)(*plVar3 + 0x60))(plVar3);
  uVar2 = FUN_0040c470(((double)iVar1 * DAT_00968e98) / _DAT_008cc878);
  FUN_005ef360(*(undefined8 *)(*(longlong *)PTR_DAT_00952838 + 0x738),uVar2);
  plVar3 = (longlong *)
           FUN_005ae7d0(*(undefined8 *)
                         (*(longlong *)(*(longlong *)PTR_DAT_00953178 + 0x738) + 0x338));
  iVar1 = (**(code **)(*plVar3 + 0x48))(plVar3);
  uVar2 = FUN_0040c470(((double)iVar1 * DAT_00968e98) / _DAT_008cc878);
  FUN_005ef3c0(*(undefined8 *)(*(longlong *)PTR_DAT_00952838 + 0x738),uVar2);
  FUN_006a6910(*(undefined8 *)(*(longlong *)PTR_DAT_00952838 + 0x738),1);
  FUN_005f0ba0(*(undefined8 *)(*(longlong *)PTR_DAT_00952838 + 0x738));
  FUN_005ef3c0(*(undefined8 *)PTR_DAT_00952838,*(undefined4 *)(*(longlong *)PTR_DAT_00953178 + 0x9c)
              );
  FUN_0072a360(*(undefined8 *)(*(longlong *)PTR_DAT_00952838 + 0x4f0),
               *(undefined4 *)(*(longlong *)(*(longlong *)PTR_DAT_00953178 + 0x4f0) + 0x14));
  FUN_0072a360(*(undefined8 *)(*(longlong *)PTR_DAT_00952838 + 0x4d8),
               *(undefined4 *)(*(longlong *)(*(longlong *)PTR_DAT_00953178 + 0x4d8) + 0x14));
  FUN_00712250(*(undefined8 *)(*(longlong *)PTR_DAT_00952838 + 0x778),1);
  FUN_00712250(*(undefined8 *)(*(longlong *)PTR_DAT_00952838 + 0x768),1);
  return;
}

/* Additional alignment helper expansion. */

/* ==================================================
 * Function: FUN_00864bb0
 * Address:  00864bb0
 * Namespace: Global
 * ================================================== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

void FUN_00864bb0(longlong param_1,undefined8 param_2,undefined8 param_3,ushort param_4)

{
  undefined2 uVar1;
  int iVar2;
  undefined8 uVar3;
  double dVar4;
  byte local_res20;
  undefined1 auStack_58 [32];
  double local_38;
  ushort local_1a;
  
  iVar2 = (**(code **)(**(longlong **)(param_1 + 0xa0) + 0x60))(*(longlong **)(param_1 + 0xa0));
  dVar4 = (double)iVar2 * _DAT_00865310;
  iVar2 = (**(code **)(**(longlong **)(param_1 + 0xa0) + 0x48))(*(longlong **)(param_1 + 0xa0));
  uVar3 = FUN_0040c460(dVar4 * dVar4 + (double)iVar2 * _DAT_00865310 * (double)iVar2 * _DAT_00865310
                      );
  *(undefined8 *)(param_1 + 0x98) = uVar3;
  local_res20 = (byte)param_4;
  *(double *)(param_1 + 0x90) = (double)(8 >> (local_res20 & 0x1f)) / *(double *)(param_1 + 0x98);
  *(double *)(param_1 + 0x88) = (double)(6 / param_4);
  *(double *)(param_1 + 0x80) = (double)(6 / param_4);
  *(undefined8 *)(param_1 + 0x78) = 0x3fe199999999999a;
  local_1a = 1;
  *(undefined1 *)(param_1 + 0x77) = 0;
  while ((local_1a < 7 && (*(byte *)(param_1 + 0x77) < 3))) {
    if ((DAT_00962260 & 1) == 1) {
      local_38 = *(double *)(param_1 + 0x50);
      uVar1 = FUN_00864660(auStack_58,*(undefined8 *)(param_1 + 0x68),
                           *(undefined8 *)(param_1 + 0x60),*(undefined8 *)(param_1 + 0x58));
      *(undefined2 *)(param_1 + 0x4e) = uVar1;
      local_38 = *(double *)(param_1 + 0x50);
      uVar1 = FUN_00864660(auStack_58,*(undefined8 *)(param_1 + 0x68),
                           *(double *)(param_1 + 0x60) - *(double *)(param_1 + 0x90),
                           *(undefined8 *)(param_1 + 0x58));
      *(undefined2 *)(param_1 + 0x4c) = uVar1;
      local_38 = *(double *)(param_1 + 0x50);
      uVar1 = FUN_00864660(auStack_58,*(undefined8 *)(param_1 + 0x68),
                           *(double *)(param_1 + 0x60) + *(double *)(param_1 + 0x90),
                           *(undefined8 *)(param_1 + 0x58));
      *(undefined2 *)(param_1 + 0x4a) = uVar1;
      if ((*(ushort *)(param_1 + 0x4c) < *(ushort *)(param_1 + 0x4e)) ||
         (*(ushort *)(param_1 + 0x4a) < *(ushort *)(param_1 + 0x4e))) {
        if (*(ushort *)(param_1 + 0x4c) < *(ushort *)(param_1 + 0x4a)) {
          *(double *)(param_1 + 0x60) = *(double *)(param_1 + 0x60) - *(double *)(param_1 + 0x90);
        }
        else {
          *(double *)(param_1 + 0x60) = *(double *)(param_1 + 0x60) + *(double *)(param_1 + 0x90);
        }
        *(undefined1 *)(param_1 + 0x77) = 0;
      }
      else if (_DAT_00865318 < *(double *)(param_1 + 0x90) * *(double *)(param_1 + 0x98)) {
        *(double *)(param_1 + 0x90) = *(double *)(param_1 + 0x90) * _DAT_00865320;
      }
    }
    local_38 = *(double *)(param_1 + 0x50);
    uVar1 = FUN_00864660(auStack_58,*(undefined8 *)(param_1 + 0x68),*(undefined8 *)(param_1 + 0x60),
                         *(undefined8 *)(param_1 + 0x58));
    *(undefined2 *)(param_1 + 0x4e) = uVar1;
    local_38 = *(double *)(param_1 + 0x50) - *(double *)(param_1 + 0x80);
    uVar1 = FUN_00864660(auStack_58,*(undefined8 *)(param_1 + 0x68),*(undefined8 *)(param_1 + 0x60),
                         *(undefined8 *)(param_1 + 0x58));
    *(undefined2 *)(param_1 + 0x4c) = uVar1;
    local_38 = *(double *)(param_1 + 0x50) + *(double *)(param_1 + 0x80);
    uVar1 = FUN_00864660(auStack_58,*(undefined8 *)(param_1 + 0x68),*(undefined8 *)(param_1 + 0x60),
                         *(undefined8 *)(param_1 + 0x58));
    *(undefined2 *)(param_1 + 0x4a) = uVar1;
    if ((*(ushort *)(param_1 + 0x4c) < *(ushort *)(param_1 + 0x4e)) ||
       (*(ushort *)(param_1 + 0x4a) < *(ushort *)(param_1 + 0x4e))) {
      if (*(ushort *)(param_1 + 0x4c) < *(ushort *)(param_1 + 0x4a)) {
        *(double *)(param_1 + 0x50) = *(double *)(param_1 + 0x50) - *(double *)(param_1 + 0x80);
      }
      else {
        *(double *)(param_1 + 0x50) = *(double *)(param_1 + 0x50) + *(double *)(param_1 + 0x80);
      }
      *(undefined1 *)(param_1 + 0x77) = 0;
    }
    else if (_DAT_00865328 < *(double *)(param_1 + 0x80)) {
      *(double *)(param_1 + 0x80) = *(double *)(param_1 + 0x80) * _DAT_00865320;
    }
    local_38 = *(double *)(param_1 + 0x50);
    uVar1 = FUN_00864660(auStack_58,*(undefined8 *)(param_1 + 0x68),*(undefined8 *)(param_1 + 0x60),
                         *(undefined8 *)(param_1 + 0x58));
    *(undefined2 *)(param_1 + 0x4e) = uVar1;
    local_38 = *(double *)(param_1 + 0x50);
    uVar1 = FUN_00864660(auStack_58,*(undefined8 *)(param_1 + 0x68),*(undefined8 *)(param_1 + 0x60),
                         *(double *)(param_1 + 0x58) - *(double *)(param_1 + 0x88));
    *(undefined2 *)(param_1 + 0x4c) = uVar1;
    local_38 = *(double *)(param_1 + 0x50);
    uVar1 = FUN_00864660(auStack_58,*(undefined8 *)(param_1 + 0x68),*(undefined8 *)(param_1 + 0x60),
                         *(double *)(param_1 + 0x58) + *(double *)(param_1 + 0x88));
    *(undefined2 *)(param_1 + 0x4a) = uVar1;
    if ((*(ushort *)(param_1 + 0x4c) < *(ushort *)(param_1 + 0x4e)) ||
       (*(ushort *)(param_1 + 0x4a) < *(ushort *)(param_1 + 0x4e))) {
      if (*(ushort *)(param_1 + 0x4c) < *(ushort *)(param_1 + 0x4a)) {
        *(double *)(param_1 + 0x58) = *(double *)(param_1 + 0x58) - *(double *)(param_1 + 0x88);
      }
      else {
        *(double *)(param_1 + 0x58) = *(double *)(param_1 + 0x58) + *(double *)(param_1 + 0x88);
      }
      *(undefined1 *)(param_1 + 0x77) = 0;
    }
    else if (_DAT_00865328 < *(double *)(param_1 + 0x88)) {
      *(double *)(param_1 + 0x88) = *(double *)(param_1 + 0x80) * _DAT_00865320;
    }
    if ((DAT_00962260 & 2) == 2) {
      local_38 = *(double *)(param_1 + 0x50);
      uVar1 = FUN_00864660(auStack_58,*(undefined8 *)(param_1 + 0x68),
                           *(undefined8 *)(param_1 + 0x60),*(undefined8 *)(param_1 + 0x58));
      *(undefined2 *)(param_1 + 0x4e) = uVar1;
      local_38 = *(double *)(param_1 + 0x50);
      uVar1 = FUN_00864660(auStack_58,*(double *)(param_1 + 0x68) - *(double *)(param_1 + 0x78),
                           *(undefined8 *)(param_1 + 0x60),*(undefined8 *)(param_1 + 0x58));
      *(undefined2 *)(param_1 + 0x4c) = uVar1;
      local_38 = *(double *)(param_1 + 0x50);
      uVar1 = FUN_00864660(auStack_58,*(double *)(param_1 + 0x68) + *(double *)(param_1 + 0x78),
                           *(undefined8 *)(param_1 + 0x60),*(undefined8 *)(param_1 + 0x58));
      *(undefined2 *)(param_1 + 0x4a) = uVar1;
      if ((*(ushort *)(param_1 + 0x4c) < *(ushort *)(param_1 + 0x4e)) ||
         (*(ushort *)(param_1 + 0x4a) < *(ushort *)(param_1 + 0x4e))) {
        if (*(ushort *)(param_1 + 0x4c) < *(ushort *)(param_1 + 0x4a)) {
          *(double *)(param_1 + 0x68) =
               *(double *)(param_1 + 0x68) - *(double *)(param_1 + 0x78) * _DAT_00865330;
        }
        else {
          *(double *)(param_1 + 0x68) =
               *(double *)(param_1 + 0x68) + *(double *)(param_1 + 0x78) * _DAT_00865330;
        }
        *(undefined1 *)(param_1 + 0x77) = 0;
      }
      else {
        *(double *)(param_1 + 0x78) = *(double *)(param_1 + 0x78) * _DAT_00865320;
      }
    }
    local_1a = local_1a + 1;
    *(char *)(param_1 + 0x77) = *(char *)(param_1 + 0x77) + '\x01';
  }
  return;
}

/* ==================================================
 * Function: FUN_00864660
 * Address:  00864660
 * Namespace: Global
 * ================================================== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

int FUN_00864660(longlong param_1,double param_2,double param_3,double param_4,double param_5)

{
  int iVar1;
  undefined4 uVar2;
  uint uVar3;
  longlong lVar4;
  short sVar5;
  short sVar6;
  undefined1 auStack_b8 [40];
  double local_90;
  double local_88;
  double local_80;
  double local_78;
  double local_70;
  double local_68;
  double local_60;
  double local_58;
  double local_50;
  longlong local_48;
  longlong local_40;
  int local_38;
  short local_32;
  ushort local_30;
  ushort local_2e;
  ushort local_2c;
  ushort local_2a;
  ushort local_28;
  short local_26;
  ushort local_24;
  ushort local_22;
  ushort local_20;
  ushort local_1e;
  
  local_1e = *(short *)(param_1 + 0x78) * 500 + 0x4b0;
  local_28 = (**(code **)(**(longlong **)(param_1 + 0x68) + 0x60))(*(longlong **)(param_1 + 0x68));
  local_2a = (**(code **)(**(longlong **)(param_1 + 0x68) + 0x48))(*(longlong **)(param_1 + 0x68));
  FUN_0040c460((double)((uint)local_1e * (uint)local_28) / (double)local_2a);
  local_22 = FUN_0040c470();
  local_20 = FUN_0040c470((double)local_1e / (double)local_22);
  local_30 = FUN_0040c470((double)local_28 / (double)local_22);
  local_32 = FUN_0040c470((double)local_2a / (double)local_20);
  iVar1 = (**(code **)(**(longlong **)(param_1 + 0x68) + 0x60))(*(longlong **)(param_1 + 0x68));
  local_58 = (double)iVar1 / _DAT_00864b88;
  iVar1 = (**(code **)(**(longlong **)(param_1 + 0x68) + 0x48))(*(longlong **)(param_1 + 0x68));
  local_60 = (double)iVar1 / _DAT_00864b88;
  local_50 = DAT_00864b90 - param_3;
  if (*(char *)(*(longlong *)(param_1 + 0x60) + 0xaf) != '\0') {
    FUN_0046de20(param_2 * _DAT_00864b98,&local_90,&local_88);
  }
  local_38 = 0;
  local_24 = 4;
  if (3 < (ushort)(local_20 - 5)) {
    sVar5 = local_20 - 8;
    do {
      local_2e = local_32 * local_24;
      if ((double)local_2a * _DAT_00864ba0 < (double)local_2e) {
        if ((double)local_2e < (double)local_2a * _DAT_00864ba8) {
          local_40 = FUN_005b4690(*(undefined8 *)(param_1 + 0x68),local_2e);
          if (*(char *)(*(longlong *)(param_1 + 0x60) + 0xaf) == '\0') {
            uVar2 = FUN_0040c470(local_60 + (((double)local_2e + param_5) - local_60) * local_50);
            local_48 = FUN_005b4690(*(undefined8 *)(param_1 + 0x70),uVar2);
          }
          else {
            local_80 = (((double)local_2e + param_5) - local_60) * local_50;
          }
          local_26 = 4;
          if (3 < (ushort)(local_22 - 5)) {
            sVar6 = local_22 - 8;
            do {
              local_2c = local_30 * local_26 + (short)((uint)(local_24 & 1) * (uint)local_30 >> 1);
              if (((double)local_28 * _DAT_00864ba0 < (double)local_2c) &&
                 ((double)local_2c < (double)local_28 * _DAT_00864ba8)) {
                if (*(char *)(*(longlong *)(param_1 + 0x60) + 0xaf) == '\0') {
                  lVar4 = FUN_0040c470(local_58 +
                                       (((double)local_2c + param_4) - local_58) * local_50);
                  uVar3 = FUN_00864620(auStack_b8,*(undefined1 *)(local_40 + (ulonglong)local_2c),
                                       *(undefined1 *)(local_48 + lVar4));
                  local_38 = local_38 + (uVar3 & 0xff);
                }
                else {
                  local_78 = (((double)local_2c + param_4) - local_58) * local_50;
                  local_70 = (local_88 * local_78 - local_90 * local_80) + local_58;
                  local_68 = local_90 * local_78 + local_88 * local_80 + local_60;
                  uVar2 = FUN_0040c470(local_68);
                  local_48 = FUN_005b4690(*(undefined8 *)(param_1 + 0x70),uVar2);
                  lVar4 = FUN_0040c470(local_70);
                  uVar3 = FUN_00864620(auStack_b8,*(undefined1 *)(local_40 + (ulonglong)local_2c),
                                       *(undefined1 *)(local_48 + lVar4));
                  local_38 = local_38 + (uVar3 & 0xff);
                }
              }
              local_26 = local_26 + 1;
              sVar6 = sVar6 + -1;
            } while (sVar6 != 0);
          }
        }
      }
      local_24 = local_24 + 1;
      sVar5 = sVar5 + -1;
    } while (sVar5 != 0);
  }
  return local_38;
}

/* ==================================================
 * Function: FUN_00862ca0
 * Address:  00862ca0
 * Namespace: Global
 * ================================================== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

void FUN_00862ca0(longlong *param_1,int param_2,int param_3,double param_4)

{
  undefined1 uVar1;
  undefined4 uVar2;
  int iVar3;
  longlong *plVar4;
  double dVar5;
  double dVar6;
  double dVar7;
  double dVar8;
  double local_60;
  longlong local_58;
  longlong local_50;
  longlong local_48;
  int local_40;
  int local_3c;
  int local_38;
  int local_34;
  int local_30;
  int local_2c;
  int local_28;
  int local_24;
  double local_20 [2];
  
  plVar4 = (longlong *)FUN_005b31e0(PTR_PTR_005a1410,1);
  uVar2 = (**(code **)(*param_1 + 0x60))(param_1);
  (**(code **)(*plVar4 + 0x88))(plVar4,uVar2);
  uVar2 = (**(code **)(*param_1 + 0x48))(param_1);
  (**(code **)(*plVar4 + 0x70))(plVar4,uVar2);
  FUN_005b6270(plVar4,6);
  (**(code **)(*plVar4 + 0x10))(plVar4,param_1);
  FUN_0046de20(param_4 * _DAT_008631c8,&local_60,local_20);
  local_34 = (**(code **)(*plVar4 + 0x48))(plVar4);
  local_34 = local_34 + -1;
  if (-1 < local_34) {
    do {
      local_58 = FUN_005b4690(plVar4,local_34);
      local_40 = local_34 - param_3;
      local_24 = (**(code **)(*plVar4 + 0x60))(plVar4);
      local_24 = local_24 + -1;
      if (-1 < local_24) {
        do {
          local_30 = local_24 - param_2;
          dVar5 = (double)param_2 + ((double)local_30 * local_20[0] - (double)local_40 * local_60);
          local_28 = FUN_0040c570(dVar5);
          local_28 = local_28 * 3;
          local_2c = local_28 + 3;
          dVar5 = (double)FUN_0040af40(dVar5);
          dVar6 = DAT_008631d0 - dVar5;
          dVar7 = (double)param_3 + (double)local_30 * local_60 + (double)local_40 * local_20[0];
          local_3c = FUN_0040c570(dVar7);
          local_38 = local_3c + 1;
          dVar7 = (double)FUN_0040af40(dVar7);
          dVar8 = DAT_008631d0 - dVar7;
          if (-1 < local_28) {
            iVar3 = (**(code **)(*param_1 + 0x60))(param_1);
            if ((local_28 <= iVar3 * 3 + -6) && (-1 < local_3c)) {
              iVar3 = (**(code **)(*param_1 + 0x48))(param_1);
              if (local_3c <= iVar3 + -2) {
                local_50 = FUN_005b4690(param_1,local_3c);
                local_48 = FUN_005b4690(param_1,local_38);
                uVar1 = FUN_0040c470(dVar8 * ((double)*(byte *)(local_50 + local_28) * dVar6 +
                                             (double)*(byte *)(local_50 + local_2c) * dVar5) +
                                     dVar7 * ((double)*(byte *)(local_48 + local_28) * dVar6 +
                                             (double)*(byte *)(local_48 + local_2c) * dVar5));
                *(undefined1 *)(local_58 + local_24 * 3) = uVar1;
                uVar1 = FUN_0040c470(dVar8 * ((double)*(byte *)(local_50 + (local_28 + 1)) * dVar6 +
                                             (double)*(byte *)(local_50 + (local_2c + 1)) * dVar5) +
                                     dVar7 * ((double)*(byte *)(local_48 + (local_28 + 1)) * dVar6 +
                                             (double)*(byte *)(local_48 + (local_2c + 1)) * dVar5));
                *(undefined1 *)(local_58 + (local_24 * 3 + 1)) = uVar1;
                uVar1 = FUN_0040c470(dVar8 * ((double)*(byte *)(local_50 + (local_28 + 2)) * dVar6 +
                                             (double)*(byte *)(local_50 + (local_2c + 2)) * dVar5) +
                                     dVar7 * ((double)*(byte *)(local_48 + (local_28 + 2)) * dVar6 +
                                             (double)*(byte *)(local_48 + (local_2c + 2)) * dVar5));
                *(undefined1 *)(local_58 + (local_24 * 3 + 2)) = uVar1;
              }
            }
          }
          local_24 = local_24 + -1;
        } while (local_24 != -1);
      }
      local_34 = local_34 + -1;
    } while (local_34 != -1);
  }
  (**(code **)(*param_1 + 0x10))(param_1,plVar4);
  FUN_0040f6e0(plVar4);
  return;
}

/* ==================================================
 * Function: FUN_008631e0
 * Address:  008631e0
 * Namespace: Global
 * ================================================== */

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

void FUN_008631e0(longlong *param_1,double param_2,double param_3)

{
  ushort uVar1;
  undefined1 uVar2;
  ushort uVar3;
  ushort uVar4;
  short sVar5;
  ushort uVar6;
  undefined4 uVar7;
  int iVar8;
  longlong *plVar9;
  longlong lVar10;
  longlong lVar11;
  longlong lVar12;
  ushort uVar13;
  ushort uVar14;
  double dVar15;
  double dVar16;
  double dVar17;
  double dVar18;
  double dVar19;
  double dVar20;
  undefined2 local_20;
  undefined2 local_1e;
  
  if ((((_DAT_00863700 < param_2) || (param_2 < DAT_00863708)) || (_DAT_00863700 < param_3)) ||
     (param_3 < DAT_00863708)) {
    plVar9 = (longlong *)FUN_005b31e0(PTR_PTR_005a1410,1);
    (**(code **)(*plVar9 + 0x10))(plVar9,param_1);
    uVar3 = (**(code **)(*param_1 + 0x60))(param_1);
    uVar4 = (**(code **)(*param_1 + 0x48))(param_1);
    dVar15 = (double)uVar3 / _DAT_00863710;
    dVar16 = (double)uVar4 / _DAT_00863710;
    local_20 = 0;
    uVar13 = uVar4;
    do {
      dVar20 = dVar16 + ((double)local_20 - dVar16) / param_3;
      if ((_DAT_00863718 <= dVar20) && (dVar20 < (double)(int)(uVar4 - 1))) {
        lVar10 = FUN_005b4690(plVar9,local_20);
        dVar17 = (double)FUN_0040af40(dVar20);
        dVar17 = DAT_00863720 - dVar17;
        dVar18 = (double)FUN_0040af40(dVar20);
        uVar7 = FUN_0040c570(dVar20);
        lVar11 = FUN_005b4690(param_1,uVar7);
        iVar8 = FUN_0040c570(dVar20);
        lVar12 = FUN_005b4690(param_1,iVar8 + 1);
        local_1e = 0;
        uVar14 = uVar3;
        do {
          dVar20 = dVar15 + ((double)local_1e - dVar15) / param_2;
          if ((_DAT_00863718 <= dVar20) && (dVar20 < (double)(int)(uVar3 - 1))) {
            sVar5 = FUN_0040c570(dVar20);
            uVar6 = sVar5 * 3;
            dVar19 = (double)FUN_0040af40(dVar20);
            dVar19 = DAT_00863720 - dVar19;
            dVar20 = (double)FUN_0040af40(dVar20);
            uVar1 = local_1e * 3;
            uVar2 = FUN_0040c470(((double)*(byte *)(lVar11 + (ulonglong)uVar6) * dVar19 +
                                 (double)*(byte *)(lVar11 + (ulonglong)(uVar6 + 3)) * dVar20) *
                                 dVar17 + ((double)*(byte *)(lVar12 + (ulonglong)uVar6) * dVar19 +
                                          (double)*(byte *)(lVar12 + (ulonglong)(uVar6 + 3)) *
                                          dVar20) * dVar18);
            *(undefined1 *)(lVar10 + (ulonglong)uVar1) = uVar2;
            uVar2 = FUN_0040c470(((double)*(byte *)(lVar11 + (ulonglong)(uVar6 + 1)) * dVar19 +
                                 (double)*(byte *)(lVar11 + (ulonglong)(uVar6 + 4)) * dVar20) *
                                 dVar17 + ((double)*(byte *)(lVar12 + (ulonglong)(uVar6 + 1)) *
                                           dVar19 + (double)*(byte *)(lVar12 + (ulonglong)
                                                                               (uVar6 + 4)) * dVar20
                                          ) * dVar18);
            *(undefined1 *)(lVar10 + (ulonglong)(uVar1 + 1)) = uVar2;
            uVar2 = FUN_0040c470(((double)*(byte *)(lVar11 + (ulonglong)(uVar6 + 2)) * dVar19 +
                                 (double)*(byte *)(lVar11 + (ulonglong)(uVar6 + 5)) * dVar20) *
                                 dVar17 + ((double)*(byte *)(lVar12 + (ulonglong)(uVar6 + 2)) *
                                           dVar19 + (double)*(byte *)(lVar12 + (ulonglong)
                                                                               (uVar6 + 5)) * dVar20
                                          ) * dVar18);
            *(undefined1 *)(lVar10 + (ulonglong)(uVar1 + 2)) = uVar2;
          }
          local_1e = local_1e + 1;
          uVar14 = uVar14 - 1;
        } while (uVar14 != 0);
      }
      local_20 = local_20 + 1;
      uVar13 = uVar13 - 1;
    } while (uVar13 != 0);
    (**(code **)(*param_1 + 0x10))(param_1,plVar9);
    FUN_0040f6e0(plVar9);
  }
  return;
}

/* ==================================================
 * Function: FUN_00863730
 * Address:  00863730
 * Namespace: Global
 * ================================================== */

void FUN_00863730(longlong *param_1,undefined8 param_2,int param_3)

{
  ushort uVar1;
  short sVar2;
  ushort uVar3;
  short sVar4;
  longlong *plVar5;
  longlong lVar6;
  longlong lVar7;
  ushort uVar8;
  undefined2 local_2e;
  
  plVar5 = (longlong *)FUN_005b31e0(PTR_PTR_005a1410,1);
  (**(code **)(*plVar5 + 0x10))(plVar5,param_1);
  if (((int)param_2 != 0) || (param_3 != 0)) {
    sVar2 = (**(code **)(*param_1 + 0x60))(param_1);
    uVar3 = (**(code **)(*param_1 + 0x48))(param_1);
    uVar1 = (short)((ulonglong)param_2 >> 0x10) >> 0xf;
    sVar4 = ((ushort)param_2 ^ uVar1) - uVar1;
    uVar1 = sVar4 * 3;
    sVar4 = (sVar2 + -1) * 3 + sVar4 * -3;
    local_2e = 0;
    uVar8 = uVar3;
    do {
      if ((-1 < (int)((uint)local_2e + param_3)) &&
         ((int)((uint)local_2e + param_3) < (int)(uint)uVar3)) {
        lVar6 = FUN_005b4690(plVar5,local_2e);
        lVar7 = FUN_005b4690(param_1,(uint)local_2e + param_3);
        if ((int)param_2 < 1) {
          FUN_00409900(lVar7,lVar6 + (ulonglong)uVar1,sVar4);
        }
        else {
          FUN_00409900(lVar7 + (ulonglong)uVar1,lVar6,sVar4);
        }
      }
      local_2e = local_2e + 1;
      uVar8 = uVar8 - 1;
    } while (uVar8 != 0);
  }
  (**(code **)(*param_1 + 0x10))(param_1,plVar5);
  FUN_0040f6e0(plVar5);
  return;
}
