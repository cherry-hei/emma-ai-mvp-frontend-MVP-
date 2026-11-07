import { createContext, useContext, useState, useEffect, ReactNode } from "react";
import { StaffUser, getToken, clearToken, getStoredUser } from "@/lib/api";

interface AuthContextType {
  user: StaffUser | null;
  isAuthenticated: boolean;
  logout: () => void;
  setUser: (user: StaffUser) => void;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  isAuthenticated: false,
  logout: () => {},
  setUser: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUserState] = useState<StaffUser | null>(() => getStoredUser());

  const isAuthenticated = !!getToken() && !!user;

  const logout = () => {
    clearToken();
    setUserState(null);
    window.location.href = "/login";
  };

  const setUser = (nextUser: StaffUser) => {
    setUserState(nextUser);
    localStorage.setItem("emma_user", JSON.stringify(nextUser));
  };

  useEffect(() => {
    if (user) {
      localStorage.setItem("emma_user", JSON.stringify(user));
    }
  }, [user]);

  useEffect(() => {
    const handleExpired = () => {
      setUserState(null);
      window.location.href = "/login";
    };
    window.addEventListener("emma-auth-expired", handleExpired);
    return () => window.removeEventListener("emma-auth-expired", handleExpired);
  }, []);

  return (
    <AuthContext.Provider value={{ user, isAuthenticated, logout, setUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
