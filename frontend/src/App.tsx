import { lazy, Suspense } from 'react';
import type { ReactNode } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Layout from './components/layout/Layout';
import LoadingSpinner from './components/common/LoadingSpinner';
import DashboardPage from './pages/DashboardPage';
import ArticlesPage from './pages/ArticlesPage';
import SourcesPage from './pages/SourcesPage';

const ArticleDetailPage = lazy(() => import('./pages/ArticleDetailPage'));
const PromptLibraryPage = lazy(() => import('./pages/PromptLibraryPage'));
const RemotionPreviewPage = lazy(() => import('./pages/RemotionPreviewPage'));

function DeferredPage({ children }: { children: ReactNode }) {
  return <Suspense fallback={<LoadingSpinner />}>{children}</Suspense>;
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30000,
      retry: 1,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<DashboardPage />} />
            <Route path="articles" element={<ArticlesPage />} />
            <Route path="articles/:articleId" element={<DeferredPage><ArticleDetailPage /></DeferredPage>} />
            <Route path="prompts" element={<DeferredPage><PromptLibraryPage /></DeferredPage>} />
            <Route path="sources" element={<SourcesPage />} />
            <Route path="video-preview" element={<DeferredPage><RemotionPreviewPage /></DeferredPage>} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
