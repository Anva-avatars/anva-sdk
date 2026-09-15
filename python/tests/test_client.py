import io
import json
import sys
import types
import unittest
import urllib.error
from unittest.mock import patch
from anva import Anva, AnvaError, LipsyncStream, RealtimeSession

class Response:
    def __init__(self, body): self.body = body
    def __enter__(self): return self
    def __exit__(self, *_): pass
    def read(self): return json.dumps(self.body).encode()
class Socket:
    def __init__(self): self.sent = []; self.closed = False
    def send(self, text): self.sent.append(json.loads(text))
    def close(self): self.closed = True
    def __iter__(self): return iter([json.dumps({"type":"speech.state","payload":{"state":"error","code":"stale_turn"}})])
class ClientTests(unittest.TestCase):
    def setUp(self): self.client=Anva('fixture-key',base_url='https://fixture.invalid');self.requests=[]
    def open(self, req, timeout):
        self.requests.append(req)
        try: sent=json.loads(req.data or b'{}')
        except ValueError: sent={}
        return Response({'session_id':'s','service_mode':sent.get('service_mode'),'say_id':'say_1'})
    def body(self): return json.loads(self.requests[-1].data)
    def test_modes_and_canonical_preset(self):
        with patch('urllib.request.urlopen', self.open):
            for mode in ['avatar_only','byo_llm','anva_light','anva_expressive','elevenagents_max']:
                result=self.client.create_session(avatar_id='a',service_mode=mode,dynamic_expressions=False)
                self.assertEqual(result['service_mode'],mode);self.assertIs(self.body()['dynamic_expressions'],False)
            self.client.create_preset('Guide',visual_character_id='old');self.assertEqual(self.body()['avatar_id'],'old')
            with self.assertRaises(ValueError):self.client.create_session('p',avatar_id='a')
    def test_discovery_and_context(self):
        with patch('urllib.request.urlopen',self.open):
            self.client.capabilities();self.assertTrue(self.requests[-1].full_url.endswith('/capabilities'))
            self.client.billing();self.assertTrue(self.requests[-1].full_url.endswith('/billing'))
            self.client.update_context('s',{'version':1});self.assertEqual(self.body(),{'version':1})
            self.client.start_presentation('s',{'version':1});self.assertTrue(self.requests[-1].full_url.endswith('/presentation'))
    def test_pcm_contract(self):
        with patch('urllib.request.urlopen',self.open):
            self.client.start_speech('s','t');self.assertEqual(self.body()['payload']['sample_rate'],24000)
            self.client.append_speech('s','t',0,0,b'\x00\x80\xff\x7f');self.assertEqual(self.body()['payload'],{'turn_id':'t','seq':0,'start_sample':0,'data':'AID/fw=='})
            self.client.finish_speech('s','t',2);self.assertEqual(self.body()['payload']['total_samples'],2)
            for invalid in [b'',b'\0',bytes(24002)]:
                with self.assertRaises(ValueError):self.client.append_speech('s','t',0,0,invalid)
    def test_structured_error(self):
        body=json.dumps({'error':{'code':'mode_unavailable','message':'Unavailable','retryable':False}}).encode()
        with patch('urllib.request.urlopen',side_effect=urllib.error.HTTPError('fixture',503,'Unavailable',{},io.BytesIO(body))):
            with self.assertRaises(AnvaError) as result:self.client.capabilities()
            self.assertEqual(result.exception.status,503);self.assertEqual(result.exception.code,'mode_unavailable');self.assertIs(result.exception.details['retryable'],False)
    def test_bidirectional_commands(self):
        socket=Socket()
        with RealtimeSession(socket) as stream:
            stream.turn_delta('t','Hello');stream.turn_done('t');stream.update_context({'version':1});stream.start_presentation({'version':1});stream.interrupt();stream.append_speech('t',0,0,b'\1\2')
            self.assertEqual(next(iter(stream))['payload']['code'],'stale_turn')
        self.assertTrue(socket.closed)
        self.assertEqual([e['type'] for e in socket.sent],['turn.delta','turn.done','context.update','presentation.start','interrupt','speech.append'])
    def test_session_duration_limit(self):
        with patch('urllib.request.urlopen',self.open):
            self.client.create_session('p');self.assertNotIn('max_duration_seconds',self.body())
            self.client.create_session('p',max_duration_seconds=600);self.assertEqual(self.body()['max_duration_seconds'],600)
    def test_connect_authenticates_with_header(self):
        calls=[];client_mod=types.ModuleType('websockets.sync.client')
        client_mod.connect=lambda uri,**kw:calls.append((uri,kw)) or Socket()
        modules={'websockets':types.ModuleType('websockets'),'websockets.sync':types.ModuleType('websockets.sync'),'websockets.sync.client':client_mod}
        with patch.dict(sys.modules,modules):self.client.connect('s')
        uri,kw=calls[0]
        self.assertEqual(uri,'wss://fixture.invalid/api/v2/sessions/s/events')
        self.assertEqual(kw['additional_headers'],{'Authorization':'Bearer fixture-key'})
        with self.assertWarns(DeprecationWarning):self.assertTrue(self.client.events_url('s').endswith('?api_key=fixture-key'))
    def test_speech_input_say_and_lipsync_clip(self):
        with patch('urllib.request.urlopen',self.open):
            self.client.create_session(avatar_id='a',service_mode='byo_llm',speech_input='off');self.assertEqual(self.body()['speech_input'],'off')
            self.assertEqual(self.client.say('s','Welcome.',say_id='lesson-3')['say_id'],'say_1')
            self.assertTrue(self.requests[-1].full_url.endswith('/api/v2/sessions/s/say'));self.assertEqual(self.body(),{'text':'Welcome.','say_id':'lesson-3'})
            self.client.lipsync(b'\x01\x02',sample_rate=16000,preset='lowlat');req=self.requests[-1]
            self.assertEqual(req.full_url,'https://fixture.invalid/api/v2/lipsync?sample_rate=16000&preset=lowlat')
            self.assertEqual(req.data,b'\x01\x02');self.assertEqual(req.get_header('Content-type'),'audio/pcm')
            self.client.lipsync(b'RIFF');self.assertEqual(self.requests[-1].full_url,'https://fixture.invalid/api/v2/lipsync')
            self.assertEqual(self.requests[-1].get_header('Content-type'),'application/octet-stream')
        self.assertEqual(self.client.lipsync_stream_url(sample_rate=16000),'wss://fixture.invalid/api/v2/lipsync/stream?sample_rate=16000')
    def test_host_lines_wait_for_the_viewer(self):
        class LiveSocket(Socket):
            def __init__(self):
                super().__init__()
                self.frames=iter([json.dumps({"type":"session.info","payload":{"status":"pending"}}),json.dumps({"type":"session.live","payload":{"status":"active"}}),json.dumps({"type":"transcript","payload":{"role":"assistant"}})])
            def __iter__(self): return self.frames
        socket=LiveSocket()
        with RealtimeSession(socket) as stream:
            self.assertEqual(stream.wait_live()['status'],'active')
            stream.say('Welcome.',say_id='lesson-3');stream.say_delta('hint','Try ');stream.say_done('hint')
            self.assertEqual([e['type'] for e in stream],['session.info','session.live','transcript'])
        self.assertEqual(socket.sent,[{'type':'say','payload':{'text':'Welcome.','say_id':'lesson-3'}},{'type':'say.delta','payload':{'say_id':'hint','text':'Try '}},{'type':'say.done','payload':{'say_id':'hint'}}])
        ended=LiveSocket();ended.frames=iter([json.dumps({"type":"session.ended","payload":{"reason":"expired"}})])
        with self.assertRaises(RuntimeError):RealtimeSession(ended).wait_live()
    def test_lipsync_stream_sends_binary_pcm(self):
        class RawSocket:
            def __init__(self): self.sent=[]; self.closed=False
            def send(self, data): self.sent.append(data)
            def close(self): self.closed=True
            def __iter__(self): return iter([json.dumps({"type":"ready","fps":30,"delay_ms":133})])
        socket=RawSocket()
        with LipsyncStream(socket) as stream:
            self.assertEqual(next(iter(stream))['delay_ms'],133)
            stream.audio(b'\x01\x02');stream.flush()
            with self.assertRaises(ValueError):stream.audio(b'\x01')
        self.assertEqual(socket.sent,[b'\x01\x02','{"type": "flush"}']);self.assertTrue(socket.closed)
        calls=[];client_mod=types.ModuleType('websockets.sync.client')
        client_mod.connect=lambda uri,**kw:calls.append((uri,kw)) or RawSocket()
        modules={'websockets':types.ModuleType('websockets'),'websockets.sync':types.ModuleType('websockets.sync'),'websockets.sync.client':client_mod}
        with patch.dict(sys.modules,modules):self.client.connect_lipsync(sample_rate=16000)
        self.assertEqual(calls[0][0],'wss://fixture.invalid/api/v2/lipsync/stream?sample_rate=16000')
        self.assertEqual(calls[0][1]['additional_headers'],{'Authorization':'Bearer fixture-key'})
if __name__=='__main__': unittest.main()
