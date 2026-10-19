'use client';
import React, { useState, useRef } from 'react';
import { Play, Plus, Minus } from 'lucide-react';
import Navbar from '@/components/shared/Navbar';
import NeuralGlow from '@/components/ui/neural-glow';
import { motion, useScroll, useTransform, useMotionValue, useSpring } from 'framer-motion';

// --- HELPER COMPONENTS ---

const ValuePropCard = ({ icon, title, description }: { icon: string, title: string, description: string }) => (
  // Added backdrop-blur to make the card pop against the glow
  <div className="bg-dark-3/90 backdrop-blur-sm p-6 rounded-2xl border border-dark-4 shadow-lg h-full">
    <span className="text-4xl mb-4 block">{icon}</span>
    <h3 className="text-2xl font-bold text-white mb-3">{title}</h3>
    <p className="text-gray-400">{description}</p>
  </div>
);

const MagneticButton = ({ 
  children, 
  className 
}: { 
  children: React.ReactNode; 
  className?: string;
}) => {
  const ref = useRef<HTMLButtonElement>(null);
  const x = useMotionValue(0);
  const y = useMotionValue(0);

  const springX = useSpring(x, { stiffness: 150, damping: 15 });
  const springY = useSpring(y, { stiffness: 150, damping: 15 });

  const handleMouseMove = (e: React.MouseEvent<HTMLButtonElement>) => {
    if (!ref.current) return;
    const rect = ref.current.getBoundingClientRect();
    const centerX = rect.left + rect.width / 2;
    const centerY = rect.top + rect.height / 2;
    x.set((e.clientX - centerX) * 0.3);
    y.set((e.clientY - centerY) * 0.3);
  };

  const handleMouseLeave = () => {
    x.set(0);
    y.set(0);
  };

  return (
    <motion.button
      ref={ref}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      style={{ x: springX, y: springY }}
      className={className}
    >
      {children}
    </motion.button>
  );
};
// --- NEW TEAM CARD COMPONENT (4 People) ---

// --- TEAM CARD STACK COMPONENT (Updated for Clarity) ---

const teamMembers = [
  { 
    id: 1, 
    name: "Hanuma Aditya", 
    role: "Project Lead & Backend Dubbing Developer", 
    image: "/team/me.jpg" 
  },
  { 
    id: 2, 
    name: "Sagar Varma", 
    role: "Backend & Insight API Integration Specialist",
    image: "/team/friend1.jpg" 
  },
  { 
    id: 3, 
    name: "Chentan Reddy", 
    role: "Frontend & UI Developer", 
    image: "/team/dev3.jpg" 
  },
  { 
    id: 4, 
    name: "Chandan Gowda", 
    role: "Cloud Developer & Tester", 
    image: "/team/dev4.jpg" 
  },
];
const TeamCardStack = () => {
  const centerIndex = (teamMembers.length - 1) / 2;

  return (
    <div className="relative w-full h-[400px] flex justify-center items-center mt-10 perspective-1000">
      <motion.div 
        className="relative w-[200px] h-[300px] group cursor-pointer"
        initial="initial"
        whileHover="hover"
        whileTap="hover"
      >
        {teamMembers.map((member, i) => {
          const distance = Math.abs(i - centerIndex);
          
          return (
            <motion.div
              key={member.id}
              className="absolute inset-0 rounded-2xl overflow-hidden shadow-2xl border-2 border-white/10 bg-dark-2"
              style={{ 
                transformOrigin: "bottom center", 
                zIndex: 10 - Math.floor(distance), 
              }}
              // 👇 THIS MAKES THE SPECIFIC CARD POP TO FRONT
              whileHover={{
                scale: 1.1,      // Make it bigger
                rotate: 0,       // Make it straight
                zIndex: 100,     // Bring it to the very front
                y: -20,          // Move it up slightly
                transition: { duration: 0.2 }
              }}
              variants={{
                initial: { 
                  rotate: (i - centerIndex) * 5,
                  x: (i - centerIndex) * 40,
                  scale: 1 - distance * 0.05, 
                  filter: "brightness(0.8)"
                },
                hover: { 
                  // 👇 INCREASED SPREAD FROM 60 TO 120
                  rotate: (i - centerIndex) * 10, // Reduced rotation so faces are clearer
                  x: (i - centerIndex) * 120,     // Much wider spread to see faces
                  scale: 1,
                  filter: "brightness(1)",
                  transition: { type: "spring", stiffness: 200, damping: 20 }
                }
              }}
            >
              <img 
                src={member.image} 
                alt={member.name} 
                className="w-full h-full object-cover"
              />
              <div className="absolute inset-0 bg-gradient-to-t from-black/90 via-transparent to-transparent opacity-0 hover:opacity-100 transition-opacity duration-300 flex flex-col justify-end p-4">
                <p className="text-white font-bold text-lg">{member.name}</p>
                <p className="text-blue-1 text-xs font-medium">{member.role}</p>
              </div>
            </motion.div>
          );
        })}
      </motion.div>
      
      <div className="absolute -bottom-8 left-0 right-0 text-center pointer-events-none">
        <p className="text-sm text-gray-500 font-mono animate-pulse">Hover to meet the team</p>
      </div>
    </div>
  );
};
const AnimatedText = ({ text, className }: { text: string; className?: string }) => {
  const words = text.split(" ");
  
  return (
    <div className={`flex flex-wrap justify-center gap-2 ${className}`}>
      {words.map((word, i) => (
        <motion.span
          key={i}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{
            duration: 0.5,
            delay: i * 0.1,
            ease: [0.33, 1, 0.68, 1]
          }}
        >
          {word}
        </motion.span>
      ))}
    </div>
  );
};

const TabButton = ({ active, onClick, children }: { active: boolean, onClick: () => void, children: React.ReactNode }) => (
  <button
    onClick={onClick}
    className={`px-6 py-2 rounded-lg font-semibold transition ${
      active
        ? 'bg-blue-1 text-white'
        : 'bg-dark-3/80 text-gray-400 hover:bg-dark-4 hover:text-white'
    }`}
  >
    {children}
  </button>
);

const AccordionItem = ({ title, isOpen, onToggle, children }: { title: string, isOpen: boolean, onToggle: () => void, children: React.ReactNode }) => (
  <div className="bg-dark-3/80 backdrop-blur-sm rounded-lg border border-dark-4 overflow-hidden">
    <button
      onClick={onToggle}
      className="flex justify-between items-center w-full p-5 text-left"
    >
      <span className="text-lg font-semibold text-white">{title}</span>
      {isOpen ? <Minus className="w-5 h-5 text-blue-1" /> : <Plus className="w-5 h-5 text-gray-400" />}
    </button>
    <motion.div
      initial={false}
      animate={{ height: isOpen ? 'auto' : 0, opacity: isOpen ? 1 : 0 }}
      className="overflow-hidden"
    >
      <div className="p-5 pt-0">
        {children}
      </div>
    </motion.div>
  </div>
);

// --- MAIN PAGE COMPONENT ---

export default function AboutPage() {
  const [activeTab, setActiveTab] = useState('ai-features');
  const [openAccordion, setOpenAccordion] = useState<string | null>('dubbing');
  
  const videoRef = useRef(null);
  const cardsContainerRef = useRef<HTMLDivElement>(null);
  
  const { scrollYProgress: videoScroll } = useScroll({
    target: videoRef,
    offset: ["start end", "end start"]
  });
  
  const videoScale = useTransform(videoScroll, [0, 0.5, 1], [0.8, 1.2, 0.8]);
  const videoOpacity = useTransform(videoScroll, [0, 0.3, 0.7, 1], [0.3, 1, 1, 0.3]);

  const { scrollYProgress: cardsScroll } = useScroll({
    target: cardsContainerRef,
    offset: ["start start", "end end"] 
  });

  const card1X = useTransform(cardsScroll, [0, 0.3], [200, 0]);
  const card1Opacity = useTransform(cardsScroll, [0, 0.3], [0, 1]);

  const card2X = useTransform(cardsScroll, [0.2, 0.5], [200, 0]);
  const card2Opacity = useTransform(cardsScroll, [0.2, 0.5], [0, 1]);

  const card3X = useTransform(cardsScroll, [0.4, 0.7], [200, 0]);
  const card3Opacity = useTransform(cardsScroll, [0.4, 0.7], [0, 1]);

  return (
    <>
      <Navbar />
      
      {/* ✅ FIXED BACKGROUND LAYER */}
      <div className="fixed inset-0 w-full h-full bg-black -z-10">
         <NeuralGlow />
         {/* Optional overlay to darken the glow slightly if text is hard to read */}
         <div className="absolute inset-0 bg-black/20 pointer-events-none" />
      </div>
      
      {/* ✅ MAIN CONTENT: Set background to transparent so fixed layer shows through */}
      <main className="w-full bg-transparent relative z-10">
        
        {/* Hero Section */}
        <section className="relative text-white pt-28 pb-20 px-6">
          <div className="max-w-6xl mx-auto text-center">
            <motion.div 
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.5 }}
              className="inline-flex items-center justify-center w-16 h-16 mb-6 bg-blue-1 rounded-2xl shadow-lg shadow-blue-500/20"
            >
              <svg className="w-8 h-8" fill="currentColor" viewBox="0 0 20 20">
                <path d="M10 3.5a1.5 1.5 0 013 0V4a1 1 0 001 1h3a1 1 0 011 1v3a1 1 0 01-1 1h-.5a1.5 1.5 0 000 3h.5a1 1 0 011 1v3a1 1 0 01-1 1h-3a1 1 0 01-1-1v-.5a1.5 1.5 0 00-3 0v.5a1 1 0 01-1 1H6a1 1 0 01-1-1v-3a1 1 0 00-1-1h-.5a1.5 1.5 0 010-3H4a1 1 0 001-1V6a1 1 0 011-1h3a1 1 0 001-1v-.5z" />
              </svg>
            </motion.div>

            <h1 className="text-5xl md:text-6xl font-bold mb-6">
              <AnimatedText text="Introducing" />
              <br />
              <span className="text-blue-1 drop-shadow-lg">
                <AnimatedText text="Horizon Meet" className="mt-2" />
              </span>
            </h1>
            
            <motion.p 
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.8 }}
              className="text-xl text-gray-300 max-w-3xl mx-auto mb-8"
            >
              AI-powered video meetings with multi-language dubbing, automatic summaries, and enterprise-grade security. Transform your meetings with intelligent insights and seamless collaboration.
            </motion.p>

            <motion.div 
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 1 }}
              className="flex gap-4 justify-center flex-wrap"
            >
              <MagneticButton className="px-8 py-3 bg-blue-1 hover:bg-blue-600 rounded-lg font-semibold transition shadow-lg shadow-blue-500/20">
                Get started
              </MagneticButton>
              <MagneticButton className="px-8 py-3 bg-dark-3/80 hover:bg-dark-4/80 backdrop-blur-sm rounded-lg font-semibold transition border border-dark-4">
                Learn more
              </MagneticButton>
            </motion.div>
          </div>
        </section>

        {/* Video Demo Section - Using semi-transparent background */}
        <section ref={videoRef} className="bg-dark-1/30 backdrop-blur-sm py-32 px-6 overflow-hidden">
          <div className="max-w-5xl mx-auto">
            <motion.div 
              style={{ 
                scale: videoScale,
                opacity: videoOpacity
              }}
              className="relative aspect-video bg-dark-2 rounded-2xl overflow-hidden shadow-2xl border border-dark-4"
            >
              <iframe
  className="w-full h-full rounded-2xl"
  src="https://www.youtube.com/embed/x3HXcgmiE_U?rel=0&modestbranding=1"
  title="Horizon Meet Demo"
  allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
  allowFullScreen
/>
            </motion.div>
          </div>
        </section>

        {/* Three Value Props Section */}
        <section 
          ref={cardsContainerRef}
          className="bg-transparent text-white py-20 px-6 min-h-[250vh] relative"
        >
          <div className="sticky top-0 h-screen flex items-center justify-center">
            <div className="max-w-6xl mx-auto w-full">
              <div className="grid md:grid-cols-3 gap-8">
                
                <motion.div
                  style={{
                    x: card1X,
                    opacity: card1Opacity
                  }}
                >
                  <ValuePropCard
                    icon="🎙️"
                    title="Multi-Language AI Dubbing"
                    description="Transform your recordings with automatic dubbing. Our AI translates and generates natural voice-overs from Telugu, Hindi, Spanish to English, making your content accessible globally."
                  />
                </motion.div>

                <motion.div
                  style={{
                    x: card2X,
                    opacity: card2Opacity
                  }}
                >
                  <ValuePropCard
                    icon="🤖"
                    title="AI Meeting Summaries & Insights"
                    description="Get instant meeting summaries with key takeaways, action items, and timestamped chapters. Our Gemini-powered AI extracts important moments so you never miss critical information."
                  />
                </motion.div>

                <motion.div
                  style={{
                    x: card3X,
                    opacity: card3Opacity
                  }}
                >
                  <ValuePropCard
                    icon="🎥"
                    title="Enterprise-Grade Video Quality"
                    description="Experience HD video calls with Stream.io's reliable infrastructure. Secure authentication via Clerk, encrypted connections, and cloud recording ensure your meetings are professional and private."
                  />
                </motion.div>

              </div>
              
              <p className="text-center mt-12 text-blue-1 italic text-sm">
                *Built with Next.js, TypeScript, Stream.io, Supabase, Clerk, and Gemini AI
              </p>
            </div>
          </div>
        </section>

        {/* Key Features Section - Using semi-transparent background */}
        <section className="py-20 px-6 bg-dark-2/80 backdrop-blur-md border-t border-dark-4/50">
          <div className="max-w-6xl mx-auto">
            <motion.p 
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              className="text-blue-1 font-semibold mb-2 text-center"
            >
              Key features
            </motion.p>
            <motion.h2 
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: 0.1 }}
              className="text-4xl font-bold text-center mb-12 text-white"
            >
              Better results, faster. That&apos;s the power of<br />Horizon Meet AI.
            </motion.h2>

            <div className="flex gap-4 justify-center mb-8 flex-wrap">
              <TabButton 
                active={activeTab === 'ai-features'} 
                onClick={() => {
                  setActiveTab('ai-features');
                  setOpenAccordion('dubbing');
                }}
              >
                AI Features
              </TabButton>
              <TabButton 
                active={activeTab === 'video-recording'} 
                onClick={() => {
                  setActiveTab('video-recording');
                  setOpenAccordion('hd-video');
                }}
              >
                Video & Recording
              </TabButton>
              <TabButton 
                active={activeTab === 'security'} 
                onClick={() => {
                  setActiveTab('security');
                  setOpenAccordion('clerk-auth');
                }}
              >
                Security
              </TabButton>
            </div>

            <div className="grid md:grid-cols-2 gap-8 items-start">
              <div className="space-y-4">
                {/* ... (Accordion logic remains same) ... */}
                {activeTab === 'ai-features' && (
                  <>
                    <AccordionItem
                      title="Multi-language dubbing with AI"
                      isOpen={openAccordion === 'dubbing'}
                      onToggle={() => setOpenAccordion(openAccordion === 'dubbing' ? null : 'dubbing')}
                    >
                      <p className="text-gray-400">
                        Automatically dub your meeting recordings from Telugu, Hindi, Spanish, and more languages to English using Gemini 2.0 Flash AI. Natural voice synthesis creates professional audio tracks.
                      </p>
                    </AccordionItem>

                    <AccordionItem
                      title="AI-generated meeting summaries and insights"
                      isOpen={openAccordion === 'insights'}
                      onToggle={() => setOpenAccordion(openAccordion === 'insights' ? null : 'insights')}
                    >
                      <p className="text-gray-400">
                        Every meeting gets automatic AI-generated summaries with key points, action items, and timestamped chapters. Review what matters in seconds instead of watching hours of recordings.
                      </p>
                    </AccordionItem>

                    <AccordionItem
                      title="Real-time transcription and translation"
                      isOpen={openAccordion === 'transcription'}
                      onToggle={() => setOpenAccordion(openAccordion === 'transcription' ? null : 'transcription')}
                    >
                      <p className="text-gray-400">
                        Get real-time speech-to-text transcription during meetings with automatic language detection. Perfect for multilingual teams and global collaboration.
                      </p>
                    </AccordionItem>
                  </>
                )}

                {activeTab === 'video-recording' && (
                  <>
                    <AccordionItem
                      title="HD video calls with screen sharing"
                      isOpen={openAccordion === 'hd-video'}
                      onToggle={() => setOpenAccordion(openAccordion === 'hd-video' ? null : 'hd-video')}
                    >
                      <p className="text-gray-400">
                        Stream.io powers crystal-clear HD video calling with built-in screen sharing, perfect for presentations and collaborative work sessions.
                      </p>
                    </AccordionItem>

                    <AccordionItem
                      title="Automatic cloud recording"
                      isOpen={openAccordion === 'cloud-recording'}
                      onToggle={() => setOpenAccordion(openAccordion === 'cloud-recording' ? null : 'cloud-recording')}
                    >
                      <p className="text-gray-400">
                        All meetings are automatically recorded and stored securely in the cloud. Access your recordings anytime from any device with instant playback.
                      </p>
                    </AccordionItem>

                    <AccordionItem
                      title="Recording management and playback"
                      isOpen={openAccordion === 'playback'}
                      onToggle={() => setOpenAccordion(openAccordion === 'playback' ? null : 'playback')}
                    >
                      <p className="text-gray-400">
                        Organize recordings by date, search through transcripts, and jump to specific moments with timestamped chapters. Share recordings with team members easily.
                      </p>
                    </AccordionItem>
                  </>
                )}

                {activeTab === 'security' && (
                  <>
                    <AccordionItem
                      title="Secure authentication with Clerk"
                      isOpen={openAccordion === 'clerk-auth'}
                      onToggle={() => setOpenAccordion(openAccordion === 'clerk-auth' ? null : 'clerk-auth')}
                    >
                      <p className="text-gray-400">
                        Clerk provides enterprise-grade authentication with Google OAuth integration, multi-factor authentication, and session management for maximum security.
                      </p>
                    </AccordionItem>

                    <AccordionItem
                      title="End-to-end encrypted video streams"
                      isOpen={openAccordion === 'encryption'}
                      onToggle={() => setOpenAccordion(openAccordion === 'encryption' ? null : 'encryption')}
                    >
                      <p className="text-gray-400">
                        All video and audio streams are encrypted in transit using industry-standard protocols. Your meeting data is protected from unauthorized access.
                      </p>
                    </AccordionItem>

                    <AccordionItem
                      title="Secure data storage with Supabase"
                      isOpen={openAccordion === 'data-storage'}
                      onToggle={() => setOpenAccordion(openAccordion === 'data-storage' ? null : 'data-storage')}
                    >
                      <p className="text-gray-400">
                        Your meeting metadata, summaries, and transcripts are stored securely in Supabase, leveraging row-level security to ensure data privacy.
                      </p>
                    </AccordionItem>
                  </>
                )}
              </div>
              
              {/* Image column */}
              <div className="bg-dark-3/50 backdrop-blur-sm rounded-xl p-8 flex items-center justify-center min-h-[400px] border border-dark-4">
                <div className="text-center">
                  <div className="grid grid-cols-3 gap-4 mb-6">
                    <motion.div 
                      className="w-16 h-16 bg-blue-1 rounded-xl shadow-lg"
                      whileHover={{ scale: 1.1, rotate: 5 }}
                      transition={{ type: "spring", stiffness: 300 }}
                    />
                    <motion.div 
                      className="w-16 h-16 bg-purple-1 rounded-xl shadow-lg"
                      whileHover={{ scale: 1.1, rotate: 5 }}
                      transition={{ type: "spring", stiffness: 300 }}
                    />
                    <motion.div 
                      className="w-16 h-16 bg-orange-1 rounded-xl shadow-lg"
                      whileHover={{ scale: 1.1, rotate: 5 }}
                      transition={{ type: "spring", stiffness: 300 }}
                    />
                  </div>
                  <div className="space-y-2">
                    <div className="h-3 bg-dark-4/50 rounded w-32 mx-auto" />
                    <div className="h-3 bg-dark-4/50 rounded w-24 mx-auto" />
                  </div>
                  <p className="text-gray-500 mt-4 text-sm">
                    {activeTab === 'ai-features' && 'AI-Powered Features'}
                    {activeTab === 'video-recording' && 'Video & Recording'}
                    {activeTab === 'security' && 'Security & Privacy'}
                  </p>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* CTA Section - Using gradient background but made slightly transparent */}
        <section className="py-20 px-6 bg-gradient-to-r from-blue-900/20 to-purple-900/20 backdrop-blur-md border-t border-dark-4/50">
          <div className="max-w-4xl mx-auto text-center">
            <motion.h2 
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              className="text-4xl font-bold text-white mb-6"
            >
              Ready to transform your meetings?
            </motion.h2>
            <motion.p 
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: 0.1 }}
              className="text-xl text-gray-300 mb-8"
            >
              Join teams worldwide using Horizon Meet for smarter, faster, and more productive video conferences.
            </motion.p>
            <motion.div 
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: 0.2 }}
              className="flex gap-4 justify-center flex-wrap"
            >
              <MagneticButton className="px-8 py-3 bg-blue-1 hover:bg-blue-600 rounded-lg font-semibold transition">
                Get started free
              </MagneticButton>
              <MagneticButton className="px-8 py-3 bg-dark-3/80 hover:bg-dark-4/80 rounded-lg font-semibold transition">
                Schedule demo
              </MagneticButton>
            </motion.div>
          </div>
        </section>

        {/* Stats Section */}
        <section className="py-20 px-6 bg-dark-2/80 backdrop-blur-md">
          <div className="max-w-6xl mx-auto">
            <motion.h2 
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              className="text-3xl font-bold text-center text-white mb-16"
            >
              By the numbers
            </motion.h2>
            <div className="grid md:grid-cols-4 gap-8">
              {[
                { stat: '10M+', label: 'Minutes recorded' },
                { stat: '50+', label: 'Languages supported' },
                { stat: '99.9%', label: 'Uptime guarantee' },
                { stat: '1000+', label: 'Teams trust us' }
              ].map((item, i) => (
                <motion.div 
                  key={i}
                  initial={{ opacity: 0, y: 20 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ delay: i * 0.1 }}
                  className="text-center"
                >
                  <div className="text-4xl font-bold text-blue-1 mb-2">{item.stat}</div>
                  <p className="text-gray-400">{item.label}</p>
                </motion.div>
              ))}
            </div>
          </div>
        </section>

        {/* Tech Stack Section */}
        <section className="py-20 px-6 bg-transparent border-t border-dark-4/50">
          <div className="max-w-6xl mx-auto">
            <motion.h2 
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              className="text-3xl font-bold text-center text-white mb-4"
            >
              Built with cutting-edge technology
            </motion.h2>
            <motion.p 
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: 0.1 }}
              className="text-center text-gray-400 mb-12"
            >
              Enterprise-grade infrastructure and AI models powering your meetings
            </motion.p>

            <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
              {[
                { name: 'Next.js', icon: '⚡', desc: 'Modern React framework' },
                { name: 'Stream.io', icon: '📹', desc: 'Video infrastructure' },
                { name: 'Supabase', icon: '🗄️', desc: 'Database & Auth' },
                { name: 'Clerk', icon: '🔐', desc: 'Authentication' },
                { name: 'Gemini AI', icon: '🤖', desc: 'AI & Summarization' },
                { name: 'TypeScript', icon: '📘', desc: 'Type safety' }
              ].map((tech, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, y: 20 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ delay: i * 0.05 }}
                  className="bg-dark-3/80 backdrop-blur-sm border border-dark-4 rounded-lg p-6 text-center hover:border-blue-1 transition"
                >
                  <div className="text-4xl mb-3">{tech.icon}</div>
                  <h3 className="text-lg font-semibold text-white mb-2">{tech.name}</h3>
                  <p className="text-sm text-gray-400">{tech.desc}</p>
                </motion.div>
              ))}
            </div>
          </div>
        </section>

        {/* FAQ Section */}
        <section className="py-20 px-6 bg-dark-2/80 backdrop-blur-md">
          <div className="max-w-3xl mx-auto">
            <motion.h2 
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              className="text-3xl font-bold text-center text-white mb-12"
            >
              Frequently asked questions
            </motion.h2>

            <div className="space-y-4">
              {[
                {
                  q: 'What makes Horizon Meet different?',
                  a: 'Horizon Meet combines real-time video conferencing with AI-powered features like automatic dubbing, meeting summaries, and multi-language transcription in one seamless platform.'
                },
                {
                  q: 'Is my data secure?',
                  a: 'Yes! We use end-to-end encryption for all video streams, secure authentication via Clerk, and Supabase for encrypted data storage with row-level security.'
                },
                {
                  q: 'Can I use Horizon Meet for large teams?',
                  a: 'Absolutely! Built on Stream.io infrastructure, Horizon Meet scales seamlessly for teams from 2 to 1000+ participants with HD video quality.'
                },
                {
                  q: 'What languages are supported?',
                  a: 'We support 50+ languages for dubbing and transcription, including Telugu, Hindi, Spanish, English, Mandarin, and more.'
                },
                {
                  q: 'How are recordings stored?',
                  a: 'All recordings are automatically stored in secure cloud storage via Supabase. You can access them anytime with instant playback and search capabilities.'
                },
                {
                  q: 'Is there a free trial?',
                  a: 'Yes! Start with our free tier to experience core features. Upgrade anytime to unlock advanced AI features and unlimited storage.'
                }
              ].map((item, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, y: 20 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ delay: i * 0.05 }}
                >
                  <AccordionItem
                    title={item.q}
                    isOpen={openAccordion === `faq-${i}`}
                    onToggle={() => setOpenAccordion(openAccordion === `faq-${i}` ? null : `faq-${i}`)}
                  >
                    <p className="text-gray-400">{item.a}</p>
                  </AccordionItem>
                </motion.div>
              ))}
            </div>
          </div>
        </section>

        {/* Testimonials Section */}
        <section className="py-20 px-6 bg-transparent border-t border-dark-4/50">
          <div className="max-w-6xl mx-auto">
            <motion.h2 
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              className="text-3xl font-bold text-center text-white mb-4"
            >
              What our users say
            </motion.h2>
            <motion.p 
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: 0.1 }}
              className="text-center text-gray-400 mb-12"
            >
              Join thousands of teams worldwide using Horizon Meet
            </motion.p>

            <div className="grid md:grid-cols-3 gap-6">
              {[
                {
                  quote: "The AI dubbing feature is a game-changer for our international team. We can now communicate seamlessly across languages.",
                  name: "Sarah Chen",
                  role: "Product Manager, TechCorp",
                  avatar: "👩‍💼"
                },
                {
                  quote: "Meeting summaries save us hours every week. We can focus on action items instead of reviewing entire recordings.",
                  name: "Rajesh Kumar",
                  role: "Engineering Lead, StartupXYZ",
                  avatar: "👨‍💻"
                },
                {
                  quote: "Best video conferencing platform we've used. The quality is exceptional and the AI features are incredibly useful.",
                  name: "Maria Garcia",
                  role: "CEO, DesignStudio",
                  avatar: "👩‍🎨"
                }
              ].map((testimonial, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, y: 20 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ delay: i * 0.1 }}
                  className="bg-dark-3/80 backdrop-blur-sm border border-dark-4 rounded-xl p-6 hover:border-blue-1 transition"
                >
                  <p className="text-gray-300 mb-6 italic">&quot;{testimonial.quote}&quot;</p>
                  <div className="flex items-center gap-3">
                    <div className="text-3xl">{testimonial.avatar}</div>
                    <div>
                      <div className="font-semibold text-white">{testimonial.name}</div>
                      <div className="text-sm text-gray-400">{testimonial.role}</div>
                    </div>
                  </div>
                </motion.div>
              ))}
            </div>
          </div>
        </section>

        {/* Pricing Section */}
        <section className="py-20 px-6 bg-dark-2/80 backdrop-blur-md">
          <div className="max-w-6xl mx-auto">
            <motion.h2 
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              className="text-3xl font-bold text-center text-white mb-4"
            >
              Simple, transparent pricing
            </motion.h2>
            <motion.p 
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: 0.1 }}
              className="text-center text-gray-400 mb-12"
            >
              Choose the plan that&apos;s right for your team
            </motion.p>

            <div className="grid md:grid-cols-3 gap-6">
              {[
                {
                  name: "Free",
                  price: "₹0",
                  period: "/month",
                  features: [
                    "Up to 5 participants",
                    "40 min meeting limit",
                    "Basic recording",
                    "1 GB storage",
                    "Community support"
                  ],
                  cta: "Start free",
                  highlighted: false
                },
                {
                  name: "Pro",
                  price: "₹999",
                  period: "/month",
                  features: [
                    "Up to 100 participants",
                    "Unlimited meetings",
                    "AI dubbing & summaries",
                    "50 GB storage",
                    "Priority support",
                    "Advanced analytics"
                  ],
                  cta: "Start pro trial",
                  highlighted: true
                },
                {
                  name: "Enterprise",
                  price: "Custom",
                  period: "",
                  features: [
                    "Unlimited participants",
                    "Custom AI models",
                    "Unlimited storage",
                    "Dedicated support",
                    "SLA guarantee",
                    "Custom integrations"
                  ],
                  cta: "Contact sales",
                  highlighted: false
                }
              ].map((plan, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, y: 20 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ delay: i * 0.1 }}
                  className={`rounded-xl p-8 backdrop-blur-sm ${
                    plan.highlighted 
                      ? 'bg-gradient-to-br from-blue-900/40 to-purple-900/40 border-2 border-blue-1 scale-105' 
                      : 'bg-dark-3/80 border border-dark-4'
                  }`}
                >
                  {plan.highlighted && (
                    <div className="text-blue-1 text-sm font-semibold mb-2">MOST POPULAR</div>
                  )}
                  <h3 className="text-2xl font-bold text-white mb-2">{plan.name}</h3>
                  <div className="mb-6">
                    <span className="text-4xl font-bold text-white">{plan.price}</span>
                    <span className="text-gray-400">{plan.period}</span>
                  </div>
                  <ul className="space-y-3 mb-8">
                    {plan.features.map((feature, j) => (
                      <li key={j} className="flex items-start gap-2 text-gray-300">
                        <span className="text-blue-1 mt-1">✓</span>
                        <span>{feature}</span>
                      </li>
                    ))}
                  </ul>
                  <MagneticButton 
                    className={`w-full py-3 rounded-lg font-semibold transition ${
                      plan.highlighted
                        ? 'bg-blue-1 hover:bg-blue-600 text-white'
                        : 'bg-dark-4/80 hover:bg-dark-4 text-white'
                    }`}
                  >
                    {plan.cta}
                  </MagneticButton>
                </motion.div>
              ))}
            </div>
          </div>
        </section>

        {/* Final CTA */}
        <section className="py-20 px-6 bg-gradient-to-br from-blue-900/20 via-purple-900/20 to-transparent backdrop-blur-md border-t border-dark-4/50">
          <div className="max-w-4xl mx-auto text-center">
            <motion.div
              initial={{ opacity: 0, scale: 0.9 }}
              whileInView={{ opacity: 1, scale: 1 }}
              viewport={{ once: true }}
              className="mb-8"
            >
              <div className="inline-flex items-center gap-2 bg-blue-1/20 px-4 py-2 rounded-full border border-blue-1/30 mb-6">
                <span className="text-blue-1">🚀</span>
                <span className="text-blue-1 font-semibold">Limited time offer</span>
              </div>
            </motion.div>
            
            <motion.h2 
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              className="text-4xl md:text-5xl font-bold text-white mb-6"
            >
              Transform your meetings with AI
            </motion.h2>
            
            <motion.p 
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: 0.1 }}
              className="text-xl text-gray-300 mb-8"
            >
              Join thousands of teams using Horizon Meet to collaborate smarter.<br />
              Start your free trial today—no credit card required.
            </motion.p>
            
            <motion.div 
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: 0.2 }}
              className="flex gap-4 justify-center flex-wrap"
            >
              <MagneticButton className="px-10 py-4 bg-blue-1 hover:bg-blue-600 rounded-lg font-semibold text-lg transition shadow-lg shadow-blue-1/20">
                Get started free →
              </MagneticButton>
              <MagneticButton className="px-10 py-4 bg-dark-3/80 hover:bg-dark-4 rounded-lg font-semibold text-lg transition border border-dark-4">
                Watch demo
              </MagneticButton>
            </motion.div>

            <motion.p 
              initial={{ opacity: 0 }}
              whileInView={{ opacity: 1 }}
              viewport={{ once: true }}
              transition={{ delay: 0.3 }}
              className="text-sm text-gray-500 mt-6"
            >
              ✓ Free forever plan available &nbsp;•&nbsp; ✓ No credit card required &nbsp;•&nbsp; ✓ Cancel anytime
            </motion.p>
            {/* 👇 PASTE THIS EXACT LINE HERE 👇 */}
    <TeamCardStack />
          </div>
        </section>

        {/* Footer */}
        <footer className="bg-dark-1/90 backdrop-blur-md border-t border-dark-4 py-12 px-6">
          <div className="max-w-6xl mx-auto">
            <div className="grid md:grid-cols-4 gap-8 mb-8">
              <div>
                <h3 className="text-white font-bold text-lg mb-4">Horizon Meet</h3>
                <p className="text-gray-400 text-sm">
                  AI-powered video conferencing for modern teams.
                </p>
              </div>
              
              <div>
                <h4 className="text-white font-semibold mb-4">Product</h4>
                <ul className="space-y-2 text-gray-400 text-sm">
                  <li><a href="#" className="hover:text-blue-1 transition">Features</a></li>
                  <li><a href="#" className="hover:text-blue-1 transition">Pricing</a></li>
                  <li><a href="#" className="hover:text-blue-1 transition">Security</a></li>
                  <li><a href="#" className="hover:text-blue-1 transition">Roadmap</a></li>
                </ul>
              </div>
              
              <div>
                <h4 className="text-white font-semibold mb-4">Company</h4>
                <ul className="space-y-2 text-gray-400 text-sm">
                  <li><a href="#" className="hover:text-blue-1 transition">About</a></li>
                  <li><a href="#" className="hover:text-blue-1 transition">Blog</a></li>
                  <li><a href="#" className="hover:text-blue-1 transition">Careers</a></li>
                  <li><a href="#" className="hover:text-blue-1 transition">Contact</a></li>
                </ul>
              </div>
              
              <div>
                <h4 className="text-white font-semibold mb-4">Legal</h4>
                <ul className="space-y-2 text-gray-400 text-sm">
                  <li><a href="#" className="hover:text-blue-1 transition">Privacy</a></li>
                  <li><a href="#" className="hover:text-blue-1 transition">Terms</a></li>
                  <li><a href="#" className="hover:text-blue-1 transition">Cookies</a></li>
                  <li><a href="#" className="hover:text-blue-1 transition">Licenses</a></li>
                </ul>
              </div>
            </div>
            
            <div className="border-t border-dark-4 pt-8 flex flex-col md:flex-row justify-between items-center gap-4">
              <p className="text-gray-500 text-sm">
                © 2025 Horizon Meet. All rights reserved.
              </p>
              <div className="flex gap-4">
                <a href="#" className="text-gray-400 hover:text-blue-1 transition">
                  <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M24 4.557c-.883.392-1.832.656-2.828.775 1.017-.609 1.798-1.574 2.165-2.724-.951.564-2.005.974-3.127 1.195-.897-.957-2.178-1.555-3.594-1.555-3.179 0-5.515 2.966-4.797 6.045-4.091-.205-7.719-2.165-10.148-5.144-1.29 2.213-.669 5.108 1.523 6.574-.806-.026-1.566-.247-2.229-.616-.054 2.281 1.581 4.415 3.949 4.89-.693.188-1.452.232-2.224.084.626 1.956 2.444 3.379 4.6 3.419-2.07 1.623-4.678 2.348-7.29 2.04 2.179 1.397 4.768 2.212 7.548 2.212 9.142 0 14.307-7.721 13.995-14.646.962-.695 1.797-1.562 2.758-2.257z"/>
                  </svg>
                </a>
                <a href="#" className="text-gray-400 hover:text-blue-1 transition">
                  <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
                  </svg>
                </a>
                <a href="#" className="text-gray-400 hover:text-blue-1 transition">
                  <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M19 0h-14c-2.761 0-5 2.239-5 5v14c0 2.761 2.239 5 5 5h14c2.762 0 5-2.239 5-5v-14c0-2.761-2.238-5-5-5zm-11 19h-3v-11h3v11zm-1.5-12.268c-.966 0-1.75-.79-1.75-1.764s.784-1.764 1.75-1.764 1.75.79 1.75 1.764-.783 1.764-1.75 1.764zm13.5 12.268h-3v-5.604c0-3.368-4-3.113-4 0v5.604h-3v-11h3v1.765c1.396-2.586 7-2.777 7 2.476v6.759z"/>
                  </svg>
                </a>
                <a href="#" className="text-gray-400 hover:text-blue-1 transition">
                  <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838c-3.403 0-6.162 2.759-6.162 6.162s2.759 6.163 6.162 6.163 6.162-2.759 6.162-6.163c0-3.403-2.759-6.162-6.162-6.162zm0 10.162c-2.209 0-4-1.79-4-4 0-2.209 1.791-4 4-4s4 1.791 4 4c0 2.21-1.791 4-4 4zm6.406-11.845c-.796 0-1.441.645-1.441 1.44s.645 1.44 1.441 1.44c.795 0 1.439-.645 1.439-1.44s-.644-1.44-1.439-1.44z"/>
                  </svg>
                </a>
              </div>
            </div>
          </div>
        </footer>
      </main>
    </>
  );
}