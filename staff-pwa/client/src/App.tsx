import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import NotFound from "@/pages/NotFound";
import { Route, Switch } from "wouter";
import ErrorBoundary from "./components/ErrorBoundary";
import { ThemeProvider } from "./contexts/ThemeContext";
import { AuthProvider } from "./contexts/AuthContext";
import { AttentionProvider } from "./contexts/AttentionContext";
import { AppLayout } from "./components/AppLayout";
import Login from "./pages/Login";
import HomePage from "./pages/HomePage";
import TasksPage from "./pages/TasksPage";
import RosterPage from "./pages/RosterPage";
import ReportPage from "./pages/ReportPage";
import CertsPage from "./pages/CertsPage";
import RecordsPage from "./pages/RecordsPage";
import PreferencesPage from "./pages/PreferencesPage";
import MessagesPage from "./pages/MessagesPage";
import { useAuth } from "./contexts/AuthContext";
import { useEffect } from "react";
import { useLocation } from "wouter";

function AppRoutes() {
  const { isAuthenticated } = useAuth();
  const [, setLocation] = useLocation();
  useEffect(() => {
    if (!isAuthenticated) setLocation("/login");
  }, [isAuthenticated, setLocation]);
  if (!isAuthenticated) return null;
  return (
    <AppLayout>
      <Switch>
        <Route path="/" component={HomePage} />
        <Route path="/tasks" component={TasksPage} />
        <Route path="/roster" component={RosterPage} />
        <Route path="/report" component={ReportPage} />
        <Route path="/records" component={RecordsPage} />
        <Route path="/certs" component={CertsPage} />
        <Route path="/preferences" component={PreferencesPage} />
        <Route path="/messages" component={MessagesPage} />
        <Route component={NotFound} />
      </Switch>
    </AppLayout>
  );
}

function Router() {
  return (
    <Switch>
      <Route path="/login" component={Login} />
      <Route>{() => <AppRoutes />}</Route>
    </Switch>
  );
}

function App() {
  return (
    <ErrorBoundary>
      <AuthProvider>
        <ThemeProvider defaultTheme="light" switchable>
          <AttentionProvider>
            <TooltipProvider>
              <Toaster />
              <Router />
            </TooltipProvider>
          </AttentionProvider>
        </ThemeProvider>
      </AuthProvider>
    </ErrorBoundary>
  );
}

export default App;
