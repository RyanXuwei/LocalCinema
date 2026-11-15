const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const html=fs.readFileSync(path.join(__dirname,'../index.html'),'utf8');
function extract(name){const start=html.indexOf('function '+name+'(');assert(start>=0);let level=0;const brace=html.indexOf('{',start);for(let i=brace;i<html.length;i++){if(html[i]==='{')level++;if(html[i]==='}'&&--level===0)return html.slice(start,i+1)}throw Error('Missing function end')}
const buttons=new Map();function button(id){if(!buttons.has(id))buttons.set(id,{disabled:false,title:'',classList:{toggle(){}},setAttribute(k,v){this[k]=v}});return buttons.get(id)}
const first={id:'a',episodes:[{id:'a1'}]},second={id:'b',episodes:[{id:'b1'}]},third={id:'c',episodes:[{id:'c1'}]};
let candidates=[first,second,third];const opened=[],loaded=[],notices=[];
const ctx={$:button,current:first,player:{dataset:{episode:'a1'},focus(){}},filteredCatalog:()=>candidates,openPlayer:(...args)=>opened.push(args),loadEpisode:id=>loaded.push(id),showControls(){},showPlaybackNotice:message=>notices.push(message)};
vm.createContext(ctx);vm.runInContext(fs.readFileSync(path.join(__dirname,'../assets/playback-modes.js'),'utf8')+";this.afterPlayback=new PlaybackModes('series',()=>0)",ctx);
vm.runInContext(['updateEpisodeNavigation','changeEpisode','syncPlaybackModes'].map(extract).join(String.fromCharCode(10)),ctx);
ctx.updateEpisodeNavigation();assert.equal(button('nextEpisode').disabled,true,'single episode has no ordinary next');
ctx.afterPlayback.toggle('random');ctx.syncPlaybackModes();assert.equal(button('nextEpisode').disabled,false,'switching random enables next immediately');
ctx.changeEpisode(1);assert.equal(opened[0][0].id,'b');assert.equal(opened[0][1].fromStart,true);assert.equal(loaded.length,0);
ctx.current=second;ctx.player.dataset.episode='b1';ctx.changeEpisode(1);assert.equal(opened[1][0].id,'c','uses existing no-repeat random queue');
candidates=[third];ctx.current=third;ctx.player.dataset.episode='c1';ctx.updateEpisodeNavigation();assert.equal(button('nextEpisode').disabled,true);
ctx.changeEpisode(1);assert.equal(opened.length,2);assert.equal(notices.length,1,'no candidate does not escape filter');
ctx.afterPlayback.mode='series';ctx.current={id:'series',episodes:[{id:'s1'},{id:'s2'}]};ctx.player.dataset.episode='s1';ctx.updateEpisodeNavigation();assert.equal(button('nextEpisode').disabled,false);ctx.changeEpisode(1);assert.equal(loaded[0],'s2');
ctx.current=null;ctx.updateEpisodeNavigation();assert.equal(button('nextEpisode').disabled,true);
console.log('PASS: mode toggle, filtered random next, no-repeat queue and ordinary episode navigation');
