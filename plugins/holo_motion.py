"""Assistant-accessible entry point into the local Holo Motion application."""
PLUGIN = {
    'name':'holo_motion', 'tier':'core',
    'description': 'Abre a aplicação Holo Motion do ULTRON: holograma 3D do corpo seguindo movimentos pela webcam, processado localmente. Use open para abrir a janela, start para iniciar rastreamento quando solicitado, stop para desligar a câmera, close para fechar, status para consultar o estado real. Não usa o screen_process: esse é outro recurso. Ex.: abrir holograma, rastrear meus movimentos, iniciar Holo Motion, parar rastreamento. A câmera pode demorar para iniciar; confirmação de solicitação não significa captura ativa.',
    'parameters':{'type':'OBJECT','properties':{'action':{'type':'STRING','enum':['open','start','stop','close','status']}},'required':['action']}
}

def run(parameters,player=None,session_memory=None):
    action=parameters.get('action','open')
    if action not in {'open','start','stop','close','status'}:
        return 'Chefe, comando de holograma inválido.'
    if player is None or not hasattr(player,'hologram_control'):
        return 'Chefe, Holo Motion requer a interface desktop do ULTRON.'
    if action=='status':return player.hologram_status()
    player.hologram_control(action)
    messages={'open':'Solicitei a abertura do Holo Motion, Chefe. A captura só começa ao iniciar o rastreamento.',
              'start':'Solicitei o início do Holo Motion com a webcam, Chefe. O painel mostrará se a câmera e o rastreamento ficaram ativos.',
              'stop':'Solicitei a parada do rastreamento e a liberação da câmera, Chefe.',
              'close':'Solicitei o fechamento do Holo Motion e a liberação da câmera, Chefe.'}
    return messages[action]
