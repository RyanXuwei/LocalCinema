/* Reuse the existing controls; this layer only arranges navigation. */
(() => {
    const navIcon = (name, label) => icon(name) + '<span>' + label + '</span>';
    const slots = $('libraryNavSlots');
    for (const id of ['allView','favView','historyView']) slots.append($(id));
    $('homeNav').innerHTML = navIcon('home','首頁');
    $('allView').innerHTML = navIcon('library','影片庫');
    $('favView').innerHTML = navIcon('heart','收藏');
    $('historyView').innerHTML = navIcon('history','觀看記錄');
    $('shortNav').innerHTML = navIcon('shorts','Short');
    $('groupNav').innerHTML = navIcon('channels','片源群組');
    $('guideNav').innerHTML = navIcon('help','使用說明');
    let allDestination = 'homeNav';
    function syncNavigation() {
        const active = view === 'favorites' ? 'favView' : view === 'history' ? 'historyView' : allDestination;
        for (const id of ['homeNav','allView','favView','historyView']) {
            const button=$(id),selected=id===active;
            button.classList.toggle('nav-active',selected);
            if(selected)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current');
        }
    }
    $('homeNav').onclick=()=>{allDestination='homeNav';setView('all');syncNavigation();window.scrollTo({top:0,behavior:'smooth'})};
    for (const id of ['allView','favView','historyView']) {
        const original=$(id).onclick;
        $(id).onclick=()=>{if(id==='allView')allDestination='allView';original();syncNavigation();$('libraryMain').scrollIntoView({block:'start',behavior:'smooth'})};
    }
    $('shortNav').onclick=()=>$('shortToggle').click();
    $('groupNav').onclick=()=>$('sourceGroupToggle').click();
    $('guideNav').onclick=()=>$('studioGuide').showModal();
    $('closeStudioGuide').onclick=()=>$('studioGuide').close();
    new MutationObserver(syncNavigation).observe($('viewTitle'),{childList:true,characterData:true,subtree:true});
    for (const [id,path] of [['heroPrevious','m14 5-7 7 7 7'],['heroNext','m10 5 7 7-7 7']]) {
        $(id).innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="'+path+'"/></svg>';
    }
    syncNavigation();
})();

/* Compact prototype toolbar: keep original controls and their handlers. */
(() => {
    const actions=document.querySelector('.headerActions');
    actions.append($('sourceGroupToggle'));
    $('homeHide').innerHTML='<svg class="playerIcon" viewBox="0 0 24 24" aria-hidden="true"><path d="M3 3l18 18M10 5c5-1 9 4 11 7l-3 4M6 6c-2 2-4 4-5 6 4 6 9 9 16 6M9 9a4 4 0 0 0 6 6"/></svg><span>Hide</span>';
    $('shortToggle').innerHTML='<svg class="playerIcon" viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="m10 8 6 4-6 4Z"/></svg><span>Short</span>';
    for(const [id,path] of [['shortPrevious','m5 15 7-7 7 7'],['shortNext','m5 9 7 7 7-7']])$(id).innerHTML='<svg class="playerIcon" viewBox="0 0 24 24" aria-hidden="true"><path d="'+path+'"/></svg>';
    $('heroPlay').innerHTML=controlIcon('play');
    $('heroPlay').setAttribute('aria-label','播放推薦影片');
    document.querySelector('.heroButtons').append(document.querySelector('.bannerIntervals'));
    $('groupNav').hidden=true;
    $('shortNav').hidden=true;
    const filters=document.querySelector('.catalogFilters');
    const advanced=document.createElement('details');advanced.className='advancedFilters';
    const summary=document.createElement('summary');summary.textContent='進階篩選';
    const panel=document.createElement('div');panel.className='advancedFilterPanel';
    advanced.append(summary,panel);
    for(const element of [...filters.children]) {
        if(['search','tagFilterDetails','sort'].includes(element.id))continue;
        panel.append(element);
    }
    panel.append(document.querySelector('.collectionActions'));
    filters.append(advanced);
    const filterPanels=[$('tagFilterDetails'),advanced];
    for(const details of filterPanels){
        details.querySelector('summary').addEventListener('click',()=>{
            if(!details.open)for(const other of filterPanels)if(other!==details)other.open=false;
        });
        details.addEventListener('toggle',()=>{
            if(details.open)for(const other of filterPanels)if(other!==details)other.open=false;
        });
    }
    document.addEventListener('pointerdown',event=>{
        for(const details of filterPanels)if(details.open&&!details.contains(event.target))details.open=false;
    });
    document.addEventListener('keydown',event=>{
        if(event.key!=='Escape')return;
        const opened=filterPanels.find(details=>details.open);
        if(!opened)return;
        event.preventDefault();event.stopPropagation();
        opened.open=false;opened.querySelector('summary').focus();
    },true);
    const views=document.createElement('div');views.className='catalogViewSwitch';
    for(const [mode,label,path] of [['grid','方格檢視','M3 3h6v6H3z M15 3h6v6h-6z M3 15h6v6H3z M15 15h6v6h-6z'],['list','列表檢視','M8 5h13M8 12h13M8 19h13M3 5h1M3 12h1M3 19h1']]){
        const button=document.createElement('button');button.title=label;button.setAttribute('aria-label',label);button.setAttribute('aria-pressed',String(mode==='grid'));
        button.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="'+path+'"/></svg>';
        button.onclick=()=>{ $('grid').classList.toggle('listView',mode==='list');for(const b of views.children)b.setAttribute('aria-pressed',String(b===button));};views.append(button);
    }
    filters.append(views);
    $('sourceGroupDialog').addEventListener('click',event=>{if(event.target===$('sourceGroupDialog')){const r=event.target.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)event.target.close();}});
    const dock=document.createElement('div');dock.className='shortDock';dock.append($('shortIntervals'));
    $('shortPanel').append(dock);
})();

function installShortStudioControls(card,box,caption,expand){
    const video=card._video,item=card._entry.item;
    const tools=document.createElement('div');tools.className='shortSideTools';
    const favorite=document.createElement('button');favorite.innerHTML=controlIcon('heart');favorite.title='收藏';favorite.setAttribute('aria-label','收藏');
    const sync=()=>favorite.setAttribute('aria-pressed',String(!!(library.find(i=>i.id===item.id)||item).favorite));sync();
    favorite.onclick=async()=>{favorite.disabled=true;try{const value=!(library.find(i=>i.id===item.id)||item).favorite;await post('/api/favorite',{id:item.id,favorite:value});item.favorite=value;const found=library.find(i=>i.id===item.id);if(found)found.favorite=value;sync();render();}catch{toast('收藏儲存失敗')}finally{favorite.disabled=false}};
    const tags=document.createElement('button');tags.innerHTML=controlIcon('tag');tags.title='設定標籤';tags.setAttribute('aria-label','設定標籤');tags.onclick=()=>openQuickTags(library.find(i=>i.id===item.id)||item);
    tools.append(favorite,tags,expand);box.append(tools);
    const timeline=document.createElement('div');timeline.className='shortTimeline';
    const clock=document.createElement('output');clock.textContent='00:00 / 00:00';
    const seek=document.createElement('input');seek.type='range';seek.min=0;seek.max=100;seek.step='.1';seek.value=0;seek.disabled=true;seek.setAttribute('aria-label','Short播放時間軸');
    const update=()=>{const duration=Number.isFinite(video.duration)?video.duration:0;seek.disabled=!duration;seek.max=duration||100;seek.value=video.currentTime||0;clock.textContent=clockTime(video.currentTime||0)+' / '+clockTime(duration)};
    video.addEventListener('timeupdate',update);video.addEventListener('loadedmetadata',update);
    seek.oninput=()=>{if(Number.isFinite(video.duration)){video.currentTime=Number(seek.value);card._position=video.currentTime;shortAdvanceClock.reset();}};
    seek.onpointerdown=()=>{shorts.holding=true};
    for(const name of ['pointerup','pointercancel','blur'])seek.addEventListener(name,()=>{shorts.holding=false});
    timeline.append(clock,seek);caption.append(timeline);
}
