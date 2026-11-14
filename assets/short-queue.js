function buildShortEntries(items) {
    const unique = new Map();
    for (const item of items) for (const episode of item.episodes || []) {
        const key = item.id + ':' + episode.id;
        if (!unique.has(key)) unique.set(key, { key, item, episode });
    }
    return [...unique.values()];
}

// Refill forever without repeating a clip within a round or at a round boundary.
class ShortQueue {
    constructor(entries, random = Math.random) {
        this.entries = entries;
        this.random = random;
        this.bag = [];
        this.last = null;
    }
    next() {
        if (!this.entries.length) return null;
        if (!this.bag.length) {
            this.bag = [...this.entries];
            for (let i = this.bag.length - 1; i > 0; i--) {
                const j = Math.floor(this.random() * (i + 1));
                [this.bag[i], this.bag[j]] = [this.bag[j], this.bag[i]];
            }
            if (this.bag.length > 1 && this.bag[0].key === this.last) {
                [this.bag[0], this.bag[1]] = [this.bag[1], this.bag[0]];
            }
        }
        const entry = this.bag.shift();
        this.last = entry.key;
        return entry;
    }
}
