"""Paired Android/Google TV control for Gabriel's TCL."""
import asyncio
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / 'config' / 'integrations' / 'tcl.json'
KEYS = {'volume_up':'VOLUME_UP', 'volume_down':'VOLUME_DOWN', 'mute':'VOLUME_MUTE',
        'home':'HOME', 'back':'BACK', 'up':'DPAD_UP', 'down':'DPAD_DOWN',
        'left':'DPAD_LEFT', 'right':'DPAD_RIGHT', 'ok':'DPAD_CENTER',
        'play_pause':'MEDIA_PLAY_PAUSE', 'power_on':'WAKEUP', 'power_off':'SLEEP'}
APPS = {'youtube':'https://www.youtube.com/tv', 'netflix':'com.netflix.ninja',
        'prime_video':'com.amazon.amazonvideo.livingroom'}
PLUGIN = {
    'name':'control_tcl_tv', 'tier':'core',
    'description': 'Controla a TV TCL Smart TV Pro de Gabriel na rede local: consultar estado, ligar/desligar, volume, navegação e abrir apps. Use somente após pedido explícito. Comando enviado não garante que o estado mudou.',
    'parameters': {'type':'OBJECT', 'properties': {
        'action': {'type':'STRING','enum':['status', *KEYS, 'open_app']},
        'app': {'type':'STRING','enum':list(APPS)},
        'steps': {'type':'INTEGER','description':'Número de passos de volume ou navegação, de 1 a 10.'},
    }, 'required':['action']},
}

async def execute(parameters):
    from androidtvremote2 import AndroidTVRemote
    action = parameters.get('action','status')
    if action not in {'status', 'open_app', *KEYS}:
        return 'Chefe, esse comando de TV não é suportado.'
    if action == 'open_app' and parameters.get('app') not in APPS:
        return 'Chefe, escolha YouTube, Netflix ou Prime Video.'
    try:
        steps=int(parameters.get('steps',1))
    except (ValueError, TypeError):
        return 'Chefe, informe de 1 a 10 passos.'
    if not 1 <= steps <= 10:
        return 'Chefe, informe de 1 a 10 passos.'
    cfg=json.loads(CONFIG.read_text())
    folder=CONFIG.parent
    if not (folder/'tcl-key.pem').exists():
        return 'Chefe, a TV ainda precisa ser pareada.'
    tv=AndroidTVRemote('ULTRON',str(folder/'tcl-cert.pem'),str(folder/'tcl-key.pem'),cfg['host'])
    try:
        await asyncio.wait_for(tv.async_connect(),10)
        if action == 'status':
            await asyncio.sleep(0.3)
            state='ligada' if tv.is_on else ('em espera' if tv.is_on is False else 'com estado ainda desconhecido')
            return f'Chefe, a TV TCL está conectada e {state}. Volume: {tv.volume_info}. Aplicativo atual: {tv.current_app or "não informado"}.'
        if action == 'open_app':
            tv.send_launch_app_command(APPS[parameters['app']])
        else:
            repeat=steps if action in {'volume_up','volume_down','up','down','left','right'} else 1
            for _ in range(repeat):
                tv.send_key_command(KEYS[action])
                await asyncio.sleep(0.12)
        await asyncio.sleep(0.3)
        return f'Chefe, enviei o comando {action} para a TV TCL.'
    finally:
        tv.disconnect()

def run(parameters, player=None, session_memory=None):
    try:
        return asyncio.run(execute(parameters))
    except Exception as exc:
        if type(exc).__name__ == 'InvalidAuth':
            return 'Chefe, a TV precisa confirmar o pareamento novamente.'
        return f'Chefe, não consegui conectar à TV TCL ({type(exc).__name__}). Verifique se está na mesma rede.'
