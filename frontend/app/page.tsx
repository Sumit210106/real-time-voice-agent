import Mic from '@/components/Mic';
import AdminDashboard from '@/components/AdminDashboard';
export default function Home() {
  return (
    <div className="min-h-screen flex justify-center items-center bg-black">
      <Mic/>
      <AdminDashboard />
    </div>
  );
}
