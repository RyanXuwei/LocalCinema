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
