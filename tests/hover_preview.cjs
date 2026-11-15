const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const html=fs.readFileSync(require('node:path').join(__dirname,'../index.html'),'utf8');
const helper=html.slice(html.indexOf('let previewRenderPending=false;'),html.indexOf('function render(){'));
const refresh=html.slice(html.indexOf('async function refresh(){'),html.indexOf('const bannerChoice='));
let now=0,next=1;const timers=new Map(),micro=[];
class Node {
 constructor(tag){this.tag=tag;this.children=[];this.style={};this.isConnected=true;this.playCount=0;this.duration=0;this.currentTime=0}
 append(...nodes){for(const n of nodes){n.parent=this;this.children.push(n)}}
 querySelector(tag){for(const n of this.children){if(n.tag===tag)return n;const child=n.querySelector?.(tag);if(child)return child}return null}
 setAttribute(){}removeAttribute(name){delete this[name]}load(){}pause(){this.paused=true}play(){this.playCount++;return Promise.resolve()}
 remove(){if(this.parent)this.parent.children=this.parent.children.filter(n=>n!==this);this.isConnected=false}
}
const item={id:'one',groups:['default'],episodes:[{id:'episode'}],title:'Synthetic'};
const grid={children:[{}]},scan={};
let payload={items:[item],groups:[],revision:2,scanning:false};
const ctx={console,document:{hidden:false,createElement:tag=>new Node(tag)},previews:new Set(),modal:{open:false},bossActive:false,
 setTimeout(fn,ms){const id=next++;timers.set(id,{fn,at:now+ms});return id},clearTimeout(id){timers.delete(id)},queueMicrotask:fn=>micro.push(fn),
 awaitPlayable:async()=>'/synthetic.mp4',openPlayer(){ctx.opened=true},renders:0,
 busy:false,wasScanning:false,coverRevision:1,library:[item],channelsUnlocked:false,shorts:{active:false},current:null,hero:item,pager:{sync(){}},
 $:id=>id==='grid'?grid:scan,fetch:async()=>({ok:true,json:async()=>payload}),syncChannelToggle(){},applyPrivacy(){},applySourceGroups:()=>false,
 applyGroupTags(){},categoryOptions(){},sourceGroupItems:()=>ctx.library,randomHero(){},resetSourceScope(){},stopShorts(){},closePlayer(){}};
vm.createContext(ctx);vm.runInContext(helper+refresh+"function render(){previewRenderPending=false;for(const stop of [...previews])stop();renders++}",ctx);
function advance(ms){now+=ms;for(const [id,t] of [...timers])if(t.at<=now){timers.delete(id);t.fn()}}
function setup(){const card=new Node('article'),visual=new Node('div');card.append(visual);ctx.installCardPreview(card,visual,item);return {card,visual}}
(async()=>{
 const {card,visual}=setup();card.onmouseenter({clientX:10,clientY:10});advance(400);card.onmousemove({clientX:11,clientY:10});advance(499);
 assert.equal(visual.children.length,0,'movement resets stationary timer');advance(1);await Promise.resolve();
 const preview=visual.children[0],video=preview.querySelector('video');assert(video);video.duration=3600;video.onloadedmetadata();assert.equal(video.currentTime,360,'long video starts at exactly 10%, without 30s cap');
 video.duration=8;video.onloadedmetadata();assert.equal(video.currentTime,.8,'short video also starts at 10%');
 advance(10000);assert.equal(visual.children[0],preview,'preview continues beyond 0.5 seconds');
 await ctx.refresh();assert.equal(ctx.renders,0,'ordinary catalog refresh defers DOM rebuild during preview');assert.equal(visual.children[0],preview);
 video.onerror();assert.equal(visual.children[0],preview,'media error remains visible rather than flashing away');
 card.onmouseleave();while(micro.length)micro.shift()();assert.equal(ctx.renders,1);assert.equal(visual.children.length,0);assert.equal(ctx.previews.size,0);
 const second=setup();second.card.onmouseenter({clientX:0,clientY:0});second.card.onmouseleave();advance(500);assert.equal(second.visual.children.length,0,'leaving cancels pending startup');
 const third=setup();third.card.onmouseenter({clientX:0,clientY:0});advance(500);await Promise.resolve();payload={...payload,items:[]};await ctx.refresh();assert.equal(third.visual.children.length,0,'removed membership stops preview immediately');
 console.log('PASS: stationary 500ms, exact 10% start, sustained preview, refresh stability, errors and cleanup');
})().catch(error=>{console.error(error);process.exitCode=1});
