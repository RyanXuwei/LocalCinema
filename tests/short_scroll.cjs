const fs=require('fs'),vm=require('vm'),assert=require('assert'),path=require('path');const html=fs.readFileSync(path.join(__dirname,'..','index.html'),'utf8');const append=html.slice(html.indexOf('function appendShortCards('),html.indexOf('\nfunction openShorts('));const start=html.indexOf('function navigateShort(');const nav=html.slice(start,html.indexOf('\n',start));
for(const nativeAnchor of [false,true]){
 let nodes=[],scroll=0,nextId=0;const frames=[];const scroller={classList:{add(){},remove(){}},get scrollTop(){return scroll},set scrollTop(v){scroll=Math.max(0,v)},insertBefore(card){nodes.push(card);card.isConnected=true}};
 const shorts={active:true,loading:false,suspended:false,cards:[],activeCard:null,queue:{next(){return {id:nextId++}}},observer:{observe(){}},sentinel:{}};
 function height(card){return 500+(card.id%3)*30}function top(card){return nodes.slice(0,nodes.indexOf(card)).reduce((n,c)=>n+height(c),0)-scroll}
 const context={shorts,$:()=>scroller,requestAnimationFrame:cb=>frames.push(cb),createShortCard:entry=>({id:entry.id,isConnected:false,getBoundingClientRect(){return {top:top(this)}},scrollIntoView(){scroll+=top(this);this.navigated=true}}),releaseShortCard:card=>{const before=top(card),h=height(card);nodes.splice(nodes.indexOf(card),1);card.isConnected=false;if(nativeAnchor&&before<0)scroll=Math.max(0,scroll-h)}};vm.createContext(context);vm.runInContext(append+'\n'+nav,context);context.appendShortCards(true);
 for(let step=0;step<60;step++){
  const current=shorts.cards[Math.min(2,shorts.cards.length-1)];shorts.activeCard=current;scroll+=top(current)-37;const before=top(current);context.appendShortCards(true);assert.equal(top(current),before,'viewport drift');assert(current.isConnected);while(frames.length)frames.shift()();
  shorts.activeCard=shorts.cards[shorts.cards.length-2];scroll+=top(shorts.activeCard);const old=shorts.activeCard.id;context.navigateShort(1);const selected=nodes.find(c=>c.navigated);assert(selected&&selected.id===old+1,'stale navigation index');selected.navigated=false;shorts.activeCard=selected;assert(shorts.cards.length<=9);
 }
}
console.log('PASS: 120 append/prune cycles preserve viewport with/without native anchoring; navigation does not skip');
