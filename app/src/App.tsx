import Navigation from './sections/Navigation';
import Hero from './sections/Hero';
import HowItWorks from './sections/HowItWorks';
import Features from './sections/Features';
import SetupGuide from './sections/SetupGuide';
import Architecture from './sections/Architecture';
import ModelComparison from './sections/ModelComparison';
import Footer from './sections/Footer';
import InstallBanner from './components/InstallBanner';

function App() {
  return (
    <div className="min-h-screen" style={{ background: '#F5F0E8' }}>
      <Navigation />
      <Hero />
      <HowItWorks />
      <Features />
      <SetupGuide />
      <Architecture />
      <ModelComparison />
      <Footer />
      <InstallBanner />
    </div>
  );
}

export default App;
