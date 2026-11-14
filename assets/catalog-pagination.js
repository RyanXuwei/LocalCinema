// Keep one shuffle for the lifetime of this page, including background refreshes.
class CatalogPager {
    constructor(size = 24, random = Math.random) {
        this.size = size;
        this.page = 1;
        this.order = [];
        this.rank = new Map();
        this.random = random;
    }
    shuffled(ids) {
        const result = [...ids];
        for (let i = result.length - 1; i > 0; i--) {
            const j = Math.floor(this.random() * (i + 1));
            [result[i], result[j]] = [result[j], result[i]];
        }
        return result;
    }
    sync(ids) {
        const unique = new Set(ids);
        this.order = this.order.filter(id => unique.has(id));
        const existing = new Set(this.order);
        this.order.push(...this.shuffled([...unique].filter(id => !existing.has(id))));
        this.rank = new Map(this.order.map((id, index) => [id, index]));
    }
    reshuffle(ids) {
        this.order = [];
        this.sync(ids);
        this.page = 1;
    }
    sort(items) {
        return [...items].sort((a, b) => this.rank.get(a.id) - this.rank.get(b.id));
    }
    slice(items) {
        const pages = Math.max(1, Math.ceil(items.length / this.size));
        this.page = Math.max(1, Math.min(pages, this.page));
        const start = (this.page - 1) * this.size;
        return { items: items.slice(start, start + this.size), pages,
            start: items.length ? start + 1 : 0, end: Math.min(start + this.size, items.length), total: items.length };
    }
}
