// Shared by catalogue rendering and the end-of-video queue.
function filterPlaybackItems(items, filters) {
    const query = (filters.query || '').toLocaleLowerCase();
    const includes = Array.isArray(filters.includeTags) ? filters.includeTags : (filters.tag ? [filters.tag] : []);
    const excludes = Array.isArray(filters.excludeTags) ? filters.excludeTags : [];
    return items.filter(item =>
        (!filters.group || (item.groups || ['default']).includes(filters.group)) &&
        (filters.view !== 'favorites' || item.favorite) &&
        (filters.view !== 'history' || item.watchCount > 0) &&
        (item.title + ' ' + (item.url || '') + ' ' + item.tags.join(' ')).toLocaleLowerCase().includes(query) &&
        (!includes.length || includes.some(tag => item.tags.includes(tag))) &&
        !excludes.some(tag => item.tags.includes(tag)) &&
        item.updated >= filters.from && item.updated <= filters.to);
}

class PlaybackModes {
    constructor(mode = 'series', random = Math.random) {
        this.mode = ['series', 'random', 'none'].includes(mode) ? mode : 'series';
        this.random = random;
        this.played = new Set();
    }
    toggle(mode) {
        if (!['series', 'random'].includes(mode)) throw new Error('Unknown playback mode');
        this.mode = this.mode === mode ? 'none' : mode;
        this.played.clear();
        return this.mode;
    }
    next(current, episodeId, filteredItems) {
        if (!current || this.mode === 'none') return null;
        if (this.mode === 'series') {
            const index = current.episodes.findIndex(episode => episode.id === episodeId);
            if (index < 0 || index + 1 >= current.episodes.length) return null;
            return { kind: 'episode', episode: current.episodes[index + 1].id };
        }
        const unique = [...new Map(filteredItems.map(item => [item.id, item])).values()];
        const candidates = unique.filter(item => item.id !== current.id && item.episodes.length);
        if (!candidates.length) return null;
        const allowed = new Set(unique.map(item => item.id));
        this.played = new Set([...this.played].filter(id => allowed.has(id)));
        this.played.add(current.id);
        let available = candidates.filter(item => !this.played.has(item.id));
        if (!available.length) {
            this.played = new Set([current.id]);
            available = candidates;
        }
        const item = available[Math.floor(this.random() * available.length)];
        this.played.add(item.id);
        return { kind: 'item', item };
    }
}
