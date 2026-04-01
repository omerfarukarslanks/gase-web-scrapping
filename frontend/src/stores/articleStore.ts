import { create } from 'zustand';
import type { ArticleFilters } from '../types/article';

interface ArticleStore {
  filters: ArticleFilters;
  setFilters: (filters: Partial<ArticleFilters>) => void;
  resetFilters: () => void;
}

const defaultFilters: ArticleFilters = {
  page: 1,
  per_page: 20,
};

export const useArticleStore = create<ArticleStore>((set) => ({
  filters: defaultFilters,
  setFilters: (newFilters) =>
    set((state) => ({
      filters: { ...state.filters, ...newFilters, page: newFilters.page ?? 1 },
    })),
  resetFilters: () => set({ filters: defaultFilters }),
}));
