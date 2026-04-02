import { Film, LibraryBig, Newspaper } from 'lucide-react';
import { Link } from 'react-router-dom';

export default function Header() {
  return (
    <header className="border-b border-slate-200 bg-white/95 px-6 py-4 backdrop-blur">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <Link to="/" className="flex items-center gap-2">
          <Newspaper className="w-6 h-6 text-blue-600" />
          <h1 className="text-xl font-bold text-gray-900">GASE News</h1>
        </Link>
        <nav className="flex flex-wrap items-center gap-3 text-sm">
          <Link to="/" className="rounded-full px-3 py-2 font-medium text-gray-600 transition hover:bg-slate-100 hover:text-gray-900">
            Dashboard
          </Link>
          <Link to="/articles" className="rounded-full px-3 py-2 font-medium text-gray-600 transition hover:bg-slate-100 hover:text-gray-900">
            Haberler
          </Link>
          <Link to="/sources" className="rounded-full px-3 py-2 font-medium text-gray-600 transition hover:bg-slate-100 hover:text-gray-900">
            Kaynaklar
          </Link>
          <Link to="/prompts" className="inline-flex items-center gap-2 rounded-full px-3 py-2 font-medium text-gray-600 transition hover:bg-slate-100 hover:text-gray-900">
            <LibraryBig className="h-4 w-4" />
            Promptlar
          </Link>
          <Link to="/video-preview" className="inline-flex items-center gap-2 rounded-full bg-slate-950 px-4 py-2 font-medium text-white transition hover:bg-slate-800">
            <Film className="h-4 w-4" />
            Video Preview
          </Link>
        </nav>
      </div>
    </header>
  );
}
