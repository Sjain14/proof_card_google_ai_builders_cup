import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import type { SignedIn } from "./auth";
import { setLang as setI18nLang, type Lang } from "./i18n";

export interface BriefDraft {
  topic: string;
  speaker: string;
  youtube: string;
  links: string;
}

interface AppState {
  lang: Lang;
  user: SignedIn | null | undefined;
  draft: BriefDraft;
  setLang: (lang: Lang) => void;
  toggleLang: () => void;
  setUser: (user: SignedIn | null | undefined) => void;
  setDraft: (patch: Partial<BriefDraft>) => void;
  clearDraft: () => void;
}

export const useAppStore = create<AppState>()(
  persist(
    (set, get) => ({
      lang: "en",
      user: undefined,
      draft: {
        topic: "",
        speaker: "",
        youtube: "",
        links: "",
      },
      setLang: (lang: Lang) => {
        setI18nLang(lang);
        set({ lang });
      },
      toggleLang: () => {
        const next = get().lang === "en" ? "hi" : "en";
        setI18nLang(next);
        set({ lang: next });
      },
      setUser: (user) => set({ user }),
      setDraft: (patch) =>
        set((state) => ({ draft: { ...state.draft, ...patch } })),
      clearDraft: () =>
        set({ draft: { topic: "", speaker: "", youtube: "", links: "" } }),
    }),
    {
      name: "proofcard_app_store",
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({ lang: state.lang, draft: state.draft }),
      onRehydrateStorage: () => (state) => {
        if (state?.lang) {
          setI18nLang(state.lang);
        }
      },
    },
  ),
);
