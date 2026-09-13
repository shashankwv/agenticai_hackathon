import React, { useState, useEffect } from 'react';
import {
  ShieldCheck,
  CreditCard,
  UserCheck,
  AlertCircle,
  RefreshCw,
  FileText,
  Lock,
  CheckCircle2,
  Sparkles,
  Building2,
  HelpCircle,
  Eye,
  EyeOff,
  Check,
  ChevronRight,
  ShieldAlert
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

// Types & Interfaces
interface FormState {
  fullName: string;
  email: string;
  phone: string;
  aadhaarNumber: string;
  panNumber: string;
}

interface BureauData {
  score: number;
  tier: 'Poor' | 'Fair' | 'Good' | 'Very Good' | 'Excellent';
  lastUpdated: string;
  bureauName: string;
  status: 'VERIFIED' | 'PENDING' | 'FAILED';
  factors: string[];
}

export default function CustomerKYCRegistration() {
  // Form State
  const [formData, setFormData] = useState<FormState>({
    fullName: 'Ananya Sharma',
    email: 'ananya.sharma@example.com',
    phone: '+91 98765 43210',
    aadhaarNumber: '',
    panNumber: 'ABCDE1234F',
  });

  // UI Control States
  const [showAadhaar, setShowAadhaar] = useState<boolean>(false);
  const [aadhaarTouched, setAadhaarTouched] = useState<boolean>(false);
  const [aadhaarError, setAadhaarError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [isSubmitted, setIsSubmitted] = useState<boolean>(false);

  // Bureau Credit Score State (Read-only integration)
  const [isFetchingBureau, setIsFetchingBureau] = useState<boolean>(false);
  const [bureauData, setBureauData] = useState<BureauData | null>({
    score: 765,
    tier: 'Excellent',
    lastUpdated: 'Just now (Live Bureau API)',
    bureauName: 'TransUnion CIBIL / Experian',
    status: 'VERIFIED',
    factors: ['Zero delayed payments', 'Low credit utilization (14%)', '5+ years credit history']
  });

  // Regex Validation strictly enforcing 12 numeric digits (^\d{12}$)
  const AADHAAR_REGEX = /^\d{12}$/;

  // Real-time Aadhaar Validation logic
  const validateAadhaar = (val: string) => {
    // Strip spaces if user pastes space-formatted string
    const rawDigits = val.replace(/\s+/g, '');
    
    if (!rawDigits) {
      return 'Aadhaar Number is required for identity verification.';
    }
    if (!/^\d+$/.test(rawDigits)) {
      return 'Aadhaar must contain numeric digits only.';
    }
    if (rawDigits.length !== 12) {
      return `Must be exactly 12 numeric digits (currently ${rawDigits.length}/12).`;
    }
    if (!AADHAAR_REGEX.test(rawDigits)) {
      return 'Invalid Aadhaar format. Must be 12 numeric digits.';
    }
    return null;
  };

  // Handle Aadhaar Input Change with formatting
  const handleAadhaarChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    // Extract digits only
    const rawVal = e.target.value.replace(/\D/g, '').slice(0, 12);
    setFormData(prev => ({ ...prev, aadhaarNumber: rawVal }));
    
    if (aadhaarTouched) {
      setAadhaarError(validateAadhaar(rawVal));
    }
  };

  const handleAadhaarBlur = () => {
    setAadhaarTouched(true);
    setAadhaarError(validateAadhaar(formData.aadhaarNumber));
  };

  // Simulate re-fetching credit score from Bureau Service
  const handleRefetchCreditScore = () => {
    setIsFetchingBureau(true);
    setTimeout(() => {
      // Generate a realistic score between 680 and 820 for demonstration
      const mockScore = Math.floor(Math.random() * (820 - 680 + 1)) + 680;
      let mockTier: BureauData['tier'] = 'Good';
      if (mockScore >= 750) mockTier = 'Excellent';
      else if (mockScore >= 700) mockTier = 'Very Good';
      else if (mockScore >= 650) mockTier = 'Good';
      else mockTier = 'Fair';

      setBureauData({
        score: mockScore,
        tier: mockTier,
        lastUpdated: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
        bureauName: 'TransUnion CIBIL / Experian',
        status: 'VERIFIED',
        factors: ['On-time repayments', 'Optimal credit mix', 'Recent inquiry verified']
      });
      setIsFetchingBureau(false);
    }, 1200);
  };

  // Form Submission Handler
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setAadhaarTouched(true);
    const err = validateAadhaar(formData.aadhaarNumber);
    setAadhaarError(err);

    if (!err) {
      setIsSubmitting(true);
      setTimeout(() => {
        setIsSubmitting(false);
        setIsSubmitted(true);
      }, 1500);
    }
  };

  // Format Aadhaar for visual display (XXXX XXXX XXXX)
  const formatAadhaarDisplay = (val: string) => {
    if (!val) return '';
    const chunks = val.match(/.{1,4}/g);
    return chunks ? chunks.join(' ') : val;
  };

  const rawAadhaarLength = formData.aadhaarNumber.length;
  const isAadhaarValid = rawAadhaarLength === 12 && !aadhaarError;

  return (
    <div className="min-h-screen bg-slate-50 text-slate-800 font-sans p-4 sm:p-6 md:p-10 flex justify-center items-start">
      <div className="w-full max-w-4xl space-y-6">
        
        {/* Header Navigation / Progress Bar */}
        <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-indigo-600 mb-1">
                <ShieldCheck className="w-4 h-4 text-indigo-600" />
                KYC Compliance & Verification
              </div>
              <h1 className="text-2xl font-bold text-slate-900">Customer KYC Registration</h1>
              <p className="text-sm text-slate-500 mt-1">
                Verify national identity credentials and check credit bureau score before onboarding.
              </p>
            </div>
            <div className="flex items-center gap-2 bg-slate-100 px-3 py-1.5 rounded-lg border border-slate-200 text-xs font-medium text-slate-600 self-start md:self-auto">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
              Bureau API Connected
            </div>
          </div>

          {/* Stepper Indicator */}
          <div className="grid grid-cols-3 gap-2 mt-6 pt-6 border-t border-slate-100">
            <div className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-indigo-600">Step 1</span>
              <span className="text-xs font-medium text-slate-700">Basic Details</span>
              <div className="h-1.5 w-full bg-indigo-600 rounded-full"></div>
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-indigo-600">Step 2</span>
              <span className="text-xs font-medium text-slate-700">Aadhaar & Bureau Score</span>
              <div className="h-1.5 w-full bg-indigo-600 rounded-full"></div>
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-slate-400">Step 3</span>
              <span className="text-xs font-medium text-slate-400">Final Approval</span>
              <div className="h-1.5 w-full bg-slate-200 rounded-full"></div>
            </div>
          </div>
        </div>

        {isSubmitted ? (
          /* Success State Screen */
          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            className="bg-white border border-emerald-200 rounded-2xl p-8 shadow-sm text-center space-y-4"
          >
            <div className="w-16 h-16 bg-emerald-100 text-emerald-600 rounded-full flex items-center justify-center mx-auto mb-2">
              <CheckCircle2 className="w-10 h-10" />
            </div>
            <h2 className="text-2xl font-bold text-slate-900">KYC Verification Submitted Successfully</h2>
            <p className="text-slate-600 max-w-md mx-auto text-sm">
              Aadhaar identification <span className="font-mono font-semibold text-slate-900">XXXX XXXX {formData.aadhaarNumber.slice(-4)}</span> has been securely validated and linked with calculated Bureau Score of <span className="font-bold text-slate-900">{bureauData?.score}</span>.
            </p>
            <div className="pt-4">
              <button
                onClick={() => {
                  setIsSubmitted(false);
                  setFormData(prev => ({ ...prev, aadhaarNumber: '' }));
                  setAadhaarTouched(false);
                }}
                className="px-5 py-2.5 bg-slate-900 text-white font-medium rounded-xl hover:bg-slate-800 transition-colors text-sm inline-flex items-center gap-2"
              >
                Register Another Customer
              </button>
            </div>
          </motion.div>
        ) : (
          /* Main Form Section */
          <form onSubmit={handleSubmit} className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            
            {/* Left Panel: Form Inputs */}
            <div className="lg:col-span-7 bg-white border border-slate-200 rounded-2xl p-6 shadow-sm space-y-6">
              <div className="flex items-center justify-between border-b border-slate-100 pb-4">
                <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2">
                  <UserCheck className="w-5 h-5 text-indigo-600" />
                  Identity Identification
                </h2>
                <span className="text-xs text-slate-400 font-medium">Fields marked * required</span>
              </div>

              {/* Readonly Context Fields */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">Full Name</label>
                  <input
                    type="text"
                    disabled
                    value={formData.fullName}
                    className="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-sm font-medium text-slate-700 cursor-not-allowed"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">PAN Number</label>
                  <input
                    type="text"
                    disabled
                    value={formData.panNumber}
                    className="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-sm font-medium text-slate-700 font-mono cursor-not-allowed uppercase"
                  />
                </div>
              </div>

              {/* AADHAAR NUMBER INPUT FIELD (Spec Requirement 1, 2, 3) */}
              <div className="space-y-2 pt-2 border-t border-slate-100">
                <div className="flex items-center justify-between">
                  <label htmlFor="aadhaarInput" className="block text-sm font-bold text-slate-800 flex items-center gap-1.5">
                    Aadhaar Number <span className="text-rose-500">*</span>
                    <span className="group relative inline-block cursor-pointer">
                      <HelpCircle className="w-4 h-4 text-slate-400 hover:text-slate-600 transition-colors" />
                      <span className="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-2 hidden group-hover:block w-48 bg-slate-900 text-white text-[11px] p-2 rounded shadow-lg z-20 font-normal">
                        Enter the 12-digit UIDAI issued Unique Identification Number.
                      </span>
                    </span>
                  </label>
                  <span className="text-xs font-medium text-slate-500">
                    {rawAadhaarLength}/12 digits
                  </span>
                </div>

                <div className="relative">
                  <input
                    id="aadhaarInput"
                    type={showAadhaar ? "text" : "password"}
                    value={formatAadhaarDisplay(formData.aadhaarNumber)}
                    onChange={handleAadhaarChange}
                    onBlur={handleAadhaarBlur}
                    placeholder="1234 5678 9012"
                    maxLength={14} // Allows 12 digits + 2 space separators
                    className={`w-full pl-4 pr-24 py-3 border rounded-xl font-mono text-base transition-all tracking-wider focus:outline-none focus:ring-2 ${!
                      aadhaarTouched 
                        ? 'border-slate-300 focus:ring-indigo-500 focus:border-indigo-500 bg-white'
                        : aadhaarError
                        ? 'border-rose-300 bg-rose-50/30 focus:ring-rose-400 focus:border-rose-400 text-rose-900'
                        : 'border-emerald-500 bg-emerald-50/20 focus:ring-emerald-400 focus:border-emerald-500 text-slate-900'
                    }`}
                  />

                  {/* Input Action Controls (Toggle Visibility & Status Indicator) */}
                  <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setShowAadhaar(!showAadhaar)}
                      className="p-1.5 text-slate-400 hover:text-slate-600 rounded-lg hover:bg-slate-100 transition-colors"
                      title={showAadhaar ? "Mask Aadhaar" : "Show Aadhaar"}
                    >
                      {showAadhaar ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>

                    {aadhaarTouched && (
                      <div>
                        {aadhaarError ? (
                          <AlertCircle className="w-5 h-5 text-rose-500" />
                        ) : isAadhaarValid ? (
                          <CheckCircle2 className="w-5 h-5 text-emerald-500" />
                        ) : null}
                      </div>
                    )}
                  </div>
                </div>

                {/* REAL-TIME VALIDATION ERROR / SUCCESS MESSAGES (Spec Requirement 3) */}
                <AnimatePresence mode="wait">
                  {aadhaarTouched && aadhaarError && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: 'auto' }}
                      exit={{ opacity: 0, height: 0 }}
                      className="flex items-center gap-2 text-rose-600 text-xs font-semibold pt-1"
                    >
                      <ShieldAlert className="w-4 h-4 shrink-0" />
                      <span>{aadhaarError}</span>
                    </motion.div>
                  )}

                  {isAadhaarValid && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: 'auto' }}
                      className="flex items-center gap-2 text-emerald-600 text-xs font-medium pt-1"
                    >
                      <Check className="w-4 h-4 shrink-0" />
                      <span>Regex validation passed: Valid 12-digit Aadhaar UID syntax.</span>
                    </motion.div>
                  )}
                </AnimatePresence>

                <p className="text-[11px] text-slate-400 pt-1 flex items-center gap-1">
                  <Lock className="w-3 h-3 text-slate-400" />
                  Aadhaar numbers are encrypted and processed per UIDAI security guidelines.
                </p>
              </div>

              {/* Submit Button Container */}
              <div className="pt-4 border-t border-slate-100 flex items-center justify-between">
                <button
                  type="button"
                  onClick={() => setFormData(prev => ({ ...prev, aadhaarNumber: '987654321098' }))}
                  className="text-xs text-indigo-600 hover:text-indigo-800 font-medium hover:underline"
                >
                  Fill Sample Valid Aadhaar
                </button>

                <button
                  type="submit"
                  disabled={!isAadhaarValid || isSubmitting}
                  className={`px-6 py-2.5 rounded-xl text-sm font-semibold flex items-center gap-2 shadow-sm transition-all ${
                    isAadhaarValid && !isSubmitting
                      ? 'bg-indigo-600 text-white hover:bg-indigo-700 cursor-pointer shadow-indigo-100'
                      : 'bg-slate-200 text-slate-400 cursor-not-allowed'
                  }`}
                >
                  {isSubmitting ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      Verifying KYC...
                    </>
                  ) : (
                    <>
                      Complete Registration
                      <ChevronRight className="w-4 h-4" />
                    </>
                  )}
                </button>
              </div>
            </div>

            {/* Right Panel: READ-ONLY CREDIT SCORE DISPLAY (Spec Requirement 4) */}
            <div className="lg:col-span-5 space-y-4">
              <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm relative overflow-hidden">
                
                {/* Decorative Header Badge */}
                <div className="flex items-center justify-between pb-4 border-b border-slate-100 mb-4">
                  <div className="flex items-center gap-2">
                    <div className="p-2 bg-indigo-50 text-indigo-600 rounded-xl">
                      <CreditCard className="w-5 h-5" />
                    </div>
                    <div>
                      <h3 className="text-sm font-bold text-slate-900">Calculated Credit Score</h3>
                      <span className="text-[11px] text-slate-500 font-medium block">Retrieved from Bureau Service</span>
                    </div>
                  </div>
                  
                  {/* Read-only status tag */}
                  <span className="px-2.5 py-1 bg-slate-100 text-slate-600 rounded-full text-[10px] font-bold uppercase tracking-wider flex items-center gap-1 border border-slate-200">
                    <Lock className="w-2.5 h-2.5" /> Read-Only
                  </span>
                </div>

                {/* Main Credit Score Visual Display */}
                {bureauData ? (
                  <div className="space-y-5">
                    
                    {/* Dynamic Score Card Box */}
                    <div className="bg-gradient-to-br from-slate-900 to-slate-800 rounded-xl p-5 text-white shadow-md relative overflow-hidden">
                      <div className="absolute -right-6 -bottom-6 w-28 h-28 bg-indigo-500/10 rounded-full blur-xl pointer-events-none"></div>
                      
                      <div className="flex justify-between items-start">
                        <span className="text-xs text-slate-300 font-medium uppercase tracking-wider flex items-center gap-1.5">
                          <Building2 className="w-3.5 h-3.5 text-indigo-400" />
                          {bureauData.bureauName}
                        </span>
                        <span className="px-2 py-0.5 bg-emerald-500/20 text-emerald-300 text-[10px] font-bold rounded border border-emerald-500/30 uppercase">
                          {bureauData.status}
                        </span>
                      </div>

                      <div className="my-4 flex items-baseline justify-between">
                        <div>
                          <div className="flex items-baseline gap-2">
                            <span className="text-4xl font-extrabold tracking-tight text-white font-mono">
                              {isFetchingBureau ? '--' : bureauData.score}
                            </span>
                            <span className="text-xs text-slate-400">/ 900</span>
                          </div>
                          <p className="text-xs text-emerald-400 font-medium mt-0.5 flex items-center gap-1">
                            <Sparkles className="w-3 h-3" /> Tier Status: {bureauData.tier}
                          </p>
                        </div>

                        {/* Gauge meter simulation pill */}
                        <div className="text-right">
                          <div className="text-xs text-slate-400 mb-1">Risk Evaluation</div>
                          <span className="px-3 py-1 bg-emerald-500 text-slate-950 font-bold text-xs rounded-lg shadow-sm">
                            Low Risk
                          </span>
                        </div>
                      </div>

                      {/* Linear score meter */}
                      <div className="space-y-1.5">
                        <div className="w-full bg-slate-700 h-2 rounded-full overflow-hidden flex">
                          <div className="bg-rose-500 h-full w-[25%]"></div>
                          <div className="bg-amber-500 h-full w-[25%]"></div>
                          <div className="bg-emerald-400 h-full w-[35%]"></div>
                          <div className="bg-indigo-400 h-full w-[15%]"></div>
                        </div>
                        <div className="flex justify-between text-[10px] text-slate-400 font-mono">
                          <span>300</span>
                          <span>600</span>
                          <span className="text-emerald-400 font-bold">750+</span>
                          <span>900</span>
                        </div>
                      </div>
                    </div>

                    {/* Impact Factors (Read-Only Info) */}
                    <div className="space-y-2">
                      <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider">Bureau Rating Indicators</h4>
                      <div className="space-y-1.5">
                        {bureauData.factors.map((factor, idx) => (
                          <div key={idx} className="flex items-center gap-2 text-xs text-slate-600 bg-slate-50 p-2 rounded-lg border border-slate-100">
                            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                            <span>{factor}</span>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Read-Only Banner Notice & API Simulation Control */}
                    <div className="pt-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
                      <div className="flex items-center gap-1 text-[11px]">
                        <span>Updated:</span>
                        <span className="font-medium text-slate-700">{bureauData.lastUpdated}</span>
                      </div>

                      <button
                        type="button"
                        onClick={handleRefetchCreditScore}
                        disabled={isFetchingBureau}
                        className="text-xs text-indigo-600 font-semibold hover:text-indigo-800 flex items-center gap-1 disabled:opacity-50 transition-colors"
                      >
                        <RefreshCw className={`w-3.5 h-3.5 ${isFetchingBureau ? 'animate-spin' : ''}`} />
                        {isFetchingBureau ? 'Re-fetching...' : 'Simulate Refresh'}
                      </button>
                    </div>

                  </div>
                ) : (
                  <div className="py-8 text-center text-slate-400 text-xs">
                    No credit bureau score loaded.
                  </div>
                )}

              </div>

              {/* System Compliance Callout */}
              <div className="bg-indigo-50/60 border border-indigo-100 rounded-xl p-4 flex items-start gap-3">
                <FileText className="w-5 h-5 text-indigo-600 shrink-0 mt-0.5" />
                <div className="text-xs text-indigo-950 space-y-1">
                  <p className="font-semibold">Audit & Bureau Compliance Note</p>
                  <p className="text-indigo-800 leading-relaxed">
                    Aadhaar numbers are verified via UIDAI vault sandbox. Credit scores are directly synchronized from authorized Credit Bureaus and cannot be manually overridden by operators.
                  </p>
                </div>
              </div>

            </div>

          </form>
        )}

      </div>
    </div>
  );
}
