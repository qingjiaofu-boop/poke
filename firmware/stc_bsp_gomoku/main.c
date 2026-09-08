#include "STC15F2K60S2.H"
#include "sys.h"
#include "adc.h"
#include "Key.h"
#include "uart1.h"
#include "displayer.h"
#include "Beep.h"
#include "Vib.h"

code unsigned long SysClock=11059200;

/* STC-B BSP 数码管段码：0~9、空白及常用字母/小数点。 */
code char decode_table[]={
    0x3f,0x06,0x5b,0x4f,0x66,0x6d,0x7d,0x07,0x7f,0x6f,
    0x00,0x08,0x40,0x01,0x41,0x48,
    0x3f|0x80,0x06|0x80,0x5b|0x80,0x4f|0x80,
    0x66|0x80,0x6d|0x80,0x7d|0x80,0x07|0x80,
    0x7f|0x80,0x6f|0x80,
    0x6d,0x3e,0x39,0x79,0x6e,0x3f,0x38,0x00
};

static unsigned char tx;
static unsigned char rx;
static unsigned char vib_cooldown=0;
static unsigned char sensor_packet[6];

static void send(unsigned char v){
    tx=v;
    if(GetUart1TxStatus()==enumUart1TxFree) Uart1Print(&tx,1);
    SetBeep(1800,8);
}

static void send_sensor_pair(unsigned int light, unsigned int temp){
    sensor_packet[0]=0x40;
    sensor_packet[1]=(unsigned char)(light>>8);
    sensor_packet[2]=(unsigned char)light;
    sensor_packet[3]=0x41;
    sensor_packet[4]=(unsigned char)(temp>>8);
    sensor_packet[5]=(unsigned char)temp;
    if(GetUart1TxStatus()==enumUart1TxFree) Uart1Print(sensor_packet,6);
}

void nav_callback(void){
    if(GetAdcNavAct(enumAdcNavKey3)==enumKeyPress) send(0x08);
    else if(GetAdcNavAct(enumAdcNavKeyUp)==enumKeyPress) send(0x01);
    else if(GetAdcNavAct(enumAdcNavKeyDown)==enumKeyPress) send(0x02);
    else if(GetAdcNavAct(enumAdcNavKeyLeft)==enumKeyPress) send(0x03);
    else if(GetAdcNavAct(enumAdcNavKeyRight)==enumKeyPress) send(0x04);
    else if(GetAdcNavAct(enumAdcNavKeyCenter)==enumKeyPress) send(0x05);
}

void key_callback(void){
    /* K1 is the game confirm key (the same action as keyboard Enter). */
    if(GetKeyAct(enumKey1)==enumKeyPress) send(0x05);
    /* K2 remains available for restart/reset in the desktop program. */
    if(GetKeyAct(enumKey2)==enumKeyPress) send(0x06);
}

/* 震动切换页面；冷却 700ms，避免一次晃动重复触发。 */
void vib_callback(void){
    if(GetVibAct()==enumVibQuake && vib_cooldown==0){
        send(0x09);
        vib_cooldown=70;
    }
}

void sys10ms_callback(void){
    if(vib_cooldown>0) vib_cooldown--;
}

void sensor_callback(void){
    struct_ADC a;
    a=GetADC();
    send_sensor_pair(a.Rop,a.Rt);
}

void uart_callback(void){
    if(rx==0x20) Seg7Print(26,27,28,28,29,26,26,33);       /* SUCCESS */
    else if(rx==0x21) Seg7Print(30,31,27,33,32,31,26,29);  /* YOU LOSE */
    else if(rx==0x22) Seg7Print(0,0,0,0,0,0,0,2);           /* difficulty */
}

void main(void){
    DisplayerInit(); BeepInit(); KeyInit(); AdcInit(ADCexpEXT); VibInit(); Uart1Init(9600);
    SetDisplayerArea(0,7); Seg7Print(0,0,0,0,0,0,0,0);
    SetUart1Rxd(&rx,1,0,0);
    SetEventCallBack(enumEventNav,nav_callback); SetEventCallBack(enumEventKey,key_callback);
    SetEventCallBack(enumEventVib,vib_callback); SetEventCallBack(enumEventSys10mS,sys10ms_callback);
    SetEventCallBack(enumEventSys1S,sensor_callback);
    SetEventCallBack(enumEventUart1Rxd,uart_callback);
    MySTC_Init(); while(1) MySTC_OS();
}
