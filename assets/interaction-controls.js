class IntervalChoice {
    constructor(seconds = 0) {
        this.seconds = [0, 5, 10, 15, 20].includes(seconds) ? seconds : 0;
    }
    toggle(seconds) {
        if (![5, 10, 15, 20].includes(seconds)) throw new Error('Unsupported interval');
        this.seconds = this.seconds === seconds ? 0 : seconds;
        return this.seconds;
    }
}

class AdvanceClock {
    constructor(choice) { this.choice = choice; this.reset(); }
    reset() { this.key = null; this.last = null; this.elapsed = 0; }
    tick(now, key, running) {
        if (key !== this.key) { this.reset(); this.key = key; }
        if (!running || !this.choice.seconds) { this.last = null; return false; }
        if (this.last !== null) this.elapsed += Math.max(0, now - this.last);
        this.last = now;
        if (this.elapsed < this.choice.seconds * 1000) return false;
        this.elapsed = 0;
        return true;
    }
}

class BannerHistory {
    constructor(limit = 80) { this.ids = []; this.index = -1; this.limit = limit; }
    record(id) {
        if (this.ids[this.index] === id) return;
        this.ids = this.ids.slice(0, this.index + 1);
        this.ids.push(id);
        if (this.ids.length > this.limit) this.ids.shift();
        this.index = this.ids.length - 1;
    }
    prepend(id) {
        if (this.ids[this.index] === id) return;
        this.ids.unshift(id);
        if (this.ids.length > this.limit) this.ids.pop();
        this.index = 0;
    }
    previous() { return this.index > 0 ? this.ids[--this.index] : null; }
    next() { return this.index + 1 < this.ids.length ? this.ids[++this.index] : null; }
    sync(ids) {
        const allowed = new Set(ids), kept = [];
        let position = -1;
        this.ids.forEach((id, index) => {
            if (allowed.has(id)) kept.push(id);
            if (index <= this.index) position = kept.length - 1;
        });
        this.ids = kept;
        this.index = kept.length ? Math.max(0, position) : -1;
    }
}

function shortScrubTime(start, dx, width, duration, fine = false) {
    if (![start, dx, width, duration].every(Number.isFinite) || duration <= 0) return 0;
    return Math.max(0, Math.min(Math.max(0, duration - .05),
        start + dx / Math.max(1, width) * duration * (fine ? .1 : 1)));
}
