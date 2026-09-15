import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Anva, AnvaError } from '../index.js';
const requests=[];
const client=new Anva('fixture-key',{baseUrl:'https://fixture.invalid'});
globalThis.fetch=async(url,options)=>{const json=options.headers['Content-Type']==='application/json';requests.push({url,options,body:options.body&&json?JSON.parse(options.body):options.body});return new Response(JSON.stringify({session_id:'s',service_mode:json?requests.at(-1).body?.service_mode:undefined,say_id:'say_1'}),{status:201});};
test('five canonical modes and compatible explicit false options reach session creation',async()=>{
 for(const serviceMode of ['avatar_only','byo_llm','anva_light','anva_expressive','elevenagents_max']){
  const result=await client.createSession({avatarId:'avatar',serviceMode,dynamicExpressions:false,performanceOptions:{performance_mode:'fast'}});
  assert.equal(result.service_mode,serviceMode);assert.equal(requests.at(-1).body.dynamic_expressions,false);
  assert.equal(requests.at(-1).options.headers.Authorization,'Bearer fixture-key');
 }
 assert.throws(()=>client.createSession({presetId:'p',avatarId:'a'}),/exactly one/);
 await client.createSession({presetId:'p',llmMode:'external'});assert.equal(requests.at(-1).body.llm_mode,'external');
 await client.createSession({presetId:'p',maxDurationSeconds:600});assert.equal(requests.at(-1).body.max_duration_seconds,600);
 assert.equal(client.eventsWsUrl('s'),'wss://fixture.invalid/api/v2/sessions/s/events');assert.match(client.eventsUrl('s'),/\?api_key=fixture-key$/);
});
test('canonical preset ID, discovery and REST presentation commands use actual endpoints',async()=>{
 await client.createPreset({name:'Guide',visualCharacterId:'legacy-avatar'});assert.equal(requests.at(-1).body.avatar_id,'legacy-avatar');
 await client.capabilities();assert.equal(requests.at(-1).url,'https://fixture.invalid/api/v2/capabilities');
 await client.billing();assert.match(requests.at(-1).url,/\/billing$/);
 await client.updateContext('s', {version:1,demo:'anva',revision:1});assert.deepEqual(requests.at(-1).body,{version:1,demo:'anva',revision:1});
 await client.startPresentation('s',{version:1,demo:'anva',revision:1});assert.match(requests.at(-1).url,/\/presentation$/);
 await client.interrupt('s');assert.match(requests.at(-1).url,/\/interrupt$/);
});
test('PCM request has exact codec, offsets, base64 and bounded bytes',async()=>{
 await client.startSpeech('s','t',{text:'Caption'});assert.deepEqual(requests.at(-1).body,{type:'speech.start',payload:{turn_id:'t',codec:'pcm_s16le',sample_rate:24000,channels:1,text:'Caption'}});
 await client.appendSpeech('s','t',0,0,new Uint8Array([0,128,255,127]));assert.deepEqual(requests.at(-1).body.payload,{turn_id:'t',seq:0,start_sample:0,data:'AID/fw=='});
 for(const pcm of [new Uint8Array(),new Uint8Array(3),new Uint8Array(24002)])assert.throws(()=>client.appendSpeech('s','t',0,0,pcm),/PCM/);
 assert.throws(()=>client.appendSpeech('s','t',-1,0,new Uint8Array(2)),/nonnegative/);
 await client.finishSpeech('s','t',2);assert.deepEqual(requests.at(-1).body,{type:'speech.done',payload:{turn_id:'t',total_samples:2}});
 await client.cancelSpeech('s','t');assert.equal(requests.at(-1).body.type,'speech.cancel');
});
test('structured HTTP error preserves status, code and retry fields',async()=>{
 const old=globalThis.fetch;globalThis.fetch=async()=>new Response(JSON.stringify({error:{code:'mode_unavailable',message:'Not configured',retryable:false}}),{status:503});
 try{await assert.rejects(client.createSession({avatarId:'a',serviceMode:'avatar_only'}),e=>e instanceof AnvaError&&e.status===503&&e.code==='mode_unavailable'&&e.details.retryable===false);}finally{globalThis.fetch=old;}
});
class FakeWS {
 static sockets=[];
 constructor(url,options){this.url=url;this.options=options;this.sent=[];this.readyState=0;FakeWS.sockets.push(this);queueMicrotask(()=>{this.readyState=1;this.onopen?.();});}
 send(data){this.sent.push(typeof data==='string'?JSON.parse(data):data);}
 close(){this.readyState=3;this.onclose?.({code:1000});}
 emit(payload){this.onmessage?.({data:JSON.stringify(payload)});}
}
test('one bidirectional socket carries commands and structured events and closes on break',async()=>{
 const stream=await client.connect('s',{WebSocketImpl:FakeWS});const socket=FakeWS.sockets.at(-1);
 assert.equal(socket.url,'wss://fixture.invalid/api/v2/sessions/s/events');assert.equal(socket.options.headers.Authorization,'Bearer fixture-key');
 await stream.turnDelta('t','Hello');await stream.turnDone('t');await stream.updateContext({version:1});await stream.startPresentation({version:1,demo:'anva',revision:1});await stream.interrupt();
 await stream.appendSpeech('t',0,0,new Uint8Array([1,2]));
 assert.deepEqual(socket.sent.map(m=>m.type),['turn.delta','turn.done','context.update','presentation.start','interrupt','speech.append']);
 socket.emit({type:'speech.state',payload:{turn_id:'t',state:'error',code:'stale_turn'}});
 for await(const event of stream){assert.equal(event.payload.code,'stale_turn');break;}
 assert.equal(socket.readyState,3);assert.equal(FakeWS.sockets.length,1);
});
test('speech input, host lines and lipsync clips reach their endpoints',async()=>{
 await client.createSession({avatarId:'a',serviceMode:'byo_llm',speechInput:'off'});assert.equal(requests.at(-1).body.speech_input,'off');
 const said=await client.say('s','Welcome.',{sayId:'lesson-3'});assert.equal(said.say_id,'say_1');
 assert.equal(requests.at(-1).url,'https://fixture.invalid/api/v2/sessions/s/say');assert.deepEqual(requests.at(-1).body,{text:'Welcome.',say_id:'lesson-3'});
 await client.lipsync(new Uint8Array([1,2,3,4]),{sampleRate:16000,preset:'lowlat'});
 const clip=requests.at(-1);assert.equal(clip.url,'https://fixture.invalid/api/v2/lipsync?sample_rate=16000&preset=lowlat');
 assert.equal(clip.options.headers['Content-Type'],'audio/pcm');assert.deepEqual([...clip.body],[1,2,3,4]);
 await client.lipsync(new Uint8Array([82,73,70,70]));assert.equal(requests.at(-1).url,'https://fixture.invalid/api/v2/lipsync');
 assert.equal(requests.at(-1).options.headers['Content-Type'],'application/octet-stream');
 assert.equal(client.lipsyncStreamUrl({sampleRate:16000}),'wss://fixture.invalid/api/v2/lipsync/stream?sample_rate=16000');
});
test('host lines wait for session.live on the realtime socket',async()=>{
 const stream=await client.connect('s',{WebSocketImpl:FakeWS});const socket=FakeWS.sockets.at(-1);
 socket.emit({type:'session.info',payload:{status:'pending'}});socket.emit({type:'session.live',payload:{status:'active'}});
 assert.equal((await stream.live).status,'active');
 await stream.say('Welcome.','lesson-3');await stream.sayDelta('hint','Try ');await stream.sayDone('hint');
 assert.deepEqual(socket.sent,[{type:'say',payload:{text:'Welcome.',say_id:'lesson-3'}},{type:'say.delta',payload:{say_id:'hint',text:'Try '}},{type:'say.done',payload:{say_id:'hint'}}]);
 const types=[];for await(const event of stream){types.push(event.type);if(types.length===2)break;}
 assert.deepEqual(types,['session.info','session.live']);
 const waiting=await client.connect('s',{WebSocketImpl:FakeWS});waiting.close();
 await assert.rejects(waiting.live,/viewer connected/);
});
test('a lipsync stream sends binary PCM and flush commands',async()=>{
 const stream=await client.connectLipsync({sampleRate:16000,preset:'lowlat',WebSocketImpl:FakeWS});const socket=FakeWS.sockets.at(-1);
 assert.equal(socket.url,'wss://fixture.invalid/api/v2/lipsync/stream?sample_rate=16000&preset=lowlat');
 assert.equal(socket.options.headers.Authorization,'Bearer fixture-key');
 await stream.audio(new Uint8Array([1,2]));await stream.flush();
 assert.ok(socket.sent[0] instanceof Uint8Array);assert.equal(socket.sent[1].type,'flush');
 assert.throws(()=>stream.audio(new Uint8Array(3)),/PCM frame/);
 socket.emit({type:'frames',start:0,values:[[0.5]]});
 for await(const message of stream){assert.equal(message.values[0][0],0.5);break;}
});
