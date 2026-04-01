import { Newspaper } from 'lucide-react';
import { Link } from 'react-router-dom';

export default function Header() {
  return (
    <header className="bg-white border-b border-gray-200 px-6 py-4">
      <div className="flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2">
          <Newspaper className="w-6 h-6 text-blue-600" />
          <h1 className="text-xl font-bold text-gray-900">GASE News</h1>
        </Link>
        <nav className="flex gap-6">
          <Link to="/" className="text-gray-600 hover:text-gray-900 font-medium">
            Dashboard
          </Link>
          <Link to="/articles" className="text-gray-600 hover:text-gray-900 font-medium">
            Haberler
          </Link>
          <Link to="/sources" className="text-gray-600 hover:text-gray-900 font-medium">
            Kaynaklar
          </Link>
        </nav>
      </div>
    </header>
  );
}
