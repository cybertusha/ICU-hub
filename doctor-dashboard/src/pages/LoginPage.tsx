import React, { useState } from 'react';
import { loginDoctor } from '../services/api';
import { UserProfile } from '../types/icu';

interface LoginPageProps {
  onSuccess: (user: UserProfile) => void;
}

export const LoginPage: React.FC<LoginPageProps> = ({ onSuccess }) => {
  const [username, setUsername] = useState('doctor');
  const [password, setPassword] = useState('doctor123');
  const [role, setRole] = useState('Doctor');
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const user = await loginDoctor(username, password, role);
      onSuccess(user);
    } catch (err: any) {
      setError(err.message || 'Authentication failed');
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-slate-100 flex flex-col items-center justify-center p-6">
      <div className="text-center mb-6">
        <h1 className="text-3xl font-extrabold text-slate-900">ICUGuardian</h1>
        <p className="text-slate-500 mt-1">Hospital-Grade Patient Monitoring System</p>
      </div>
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-md bg-white rounded-2xl border border-slate-200 p-7 shadow-lg space-y-4"
      >
        <h2 className="text-lg font-bold text-slate-900">Sign In</h2>
        {error && <div className="text-sm text-red-600 bg-red-50 p-2 rounded">{error}</div>}
        <div>
          <label className="block text-xs font-semibold text-slate-700 mb-1">Username</label>
          <input
            className="w-full bg-slate-100 rounded-lg px-3 py-2 text-sm"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
        </div>
        <div>
          <label className="block text-xs font-semibold text-slate-700 mb-1">Password</label>
          <input
            type="password"
            className="w-full bg-slate-100 rounded-lg px-3 py-2 text-sm"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        <div>
          <label className="block text-xs font-semibold text-slate-700 mb-1">Role</label>
          <select
            className="w-full bg-slate-100 rounded-lg px-3 py-2 text-sm"
            value={role}
            onChange={(e) => setRole(e.target.value)}
          >
            <option value="Doctor">Doctor</option>
            <option value="Nurse">Nurse</option>
            <option value="Admin">Admin</option>
          </select>
        </div>
        <button
          type="submit"
          className="w-full bg-slate-950 text-white rounded-lg py-2.5 text-sm font-semibold"
        >
          Sign In
        </button>
      </form>
    </div>
  );
};
