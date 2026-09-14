import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Eye,
  EyeOff,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  ShieldCheck,
  CreditCard,
  User,
  ArrowRight,
  ArrowLeft,
  Lock,
  TrendingUp,
  Sparkles,
  Building2,
  Check,
  ShieldAlert,
  Info,
  FileText
} from 'lucide-react';

const STEPS = [
  { id: 1, name: 'Personal Information', icon: User },
  { id: 2, name: 'Aadhaar Verification', icon: ShieldCheck },
  { id: 3, name: 'Credit Score Bureau', icon: TrendingUp },
  { id: 4, name: 'Final Review', icon: CheckCircle2 }
];

export default function CustomerKYCForm() {
  const [currentStep, setCurrentStep] = useState<number>(2);
  const [formData, setFormData] = useState({
    fullName: 'Ananya Sharma',
    email: 'ananya.sharma@example.com',
    phone: '9876543210',
    pan: 'ABCDE1234F',
    aadhaar: ''
  });

  // Aadhaar specific state
  const [showAadhaar, setShowAadhaar] = useState(false);
  const [aadhaarTouched, setAadhaarTouched] = useState(false);
  const [aadhaarValid, setAadhaarValid] = useState<boolean | null>(null);

  // Credit Score states
  const [creditScore, setCreditScore] = useState<number | null>(765);
  const [isFetchingScore, setIsFetchingScore] = useState(false);
  const [lastUpdated, setLastUpdated] = useState('Just now');
  const [submitted, setSubmitted] = useState(false);

  // Real-time Aadhaar validation regex: exactly 12 numeric digits
  const validateAadhaar = (value: string) => {
    const digitsOnly = value.replace(/\D/g, '');
    const isValid = /^\d{12}$/.test(digitsOnly);
    setAadhaarValid(isValid);
    return isValid;
  };

  const handleAadhaarChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const rawValue = e.target.value.replace(/\D/g, '').slice(0, 12);
    setFormData(prev => ({ ...prev, aadhaar: rawValue }));
    if (!aadhaarTouched) setAadhaarTouched(true);
    validateAadhaar(rawValue);
  };

  const handleAadhaarBlur = () => {
    setAadhaarTouched(true);
    validateAadhaar(formData.aadhaar);
  };

  const formatAadhaarDisplay = (val: string, masked: boolean) => {
    if (!val) return '';
    const parts = val.match(/.{1,4}/g) || [];
    const formatted = parts.join(' ');
    if (!masked) return formatted;
    
    // Mask first 8 digits with 'X'
    return formatted.replace(/\d/g, (char, index) => {
      // Calculate position excluding spaces
      return index < 10 ? '•' : char;
    });
  };

  const refreshCreditScore = () => {
    setIsFetchingScore(true);
    setTimeout(() => {
      const simulatedScores = [720, 755, 785, 810, 740];
      const randomScore = simulatedScores[Math.floor(Math.random() * simulatedScores.length)];
      setCreditScore(randomScore);
      setLastUpdated(new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
      setIsFetchingScore(false);
    }, 1200);
  };

  const getRiskCategory = (score: number) => {
    if (score >= 780) return { label: 'Low Risk', tier: 'Excellent', color: 'text-emerald-600', bg: 'bg-emerald-50 border-emerald-200', barColor: 'bg-emerald-500', indicator: '90%' };
    if (score >= 720) return { label: 'Low-Medium Risk', tier: 'Good', color: 'text-blue-600', bg: 'bg-blue-50 border-blue-200', barColor: 'bg-blue-500', indicator: '75%' };
    if (score >= 650) return { label: 'Medium Risk', tier: 'Fair', color: 'text-amber-600', bg: 'bg-amber-50 border-amber-200', barColor: 'bg-amber-500', indicator: '50%' };
    return { label: 'High Risk', tier: 'Poor', color: 'text-rose-600', bg: 'bg-rose-50 border-rose-200', barColor: 'bg-rose-500', indicator: '25%' };
  };

  const canProceedFromStep2 = aadhaarValid === true;

  const handleNext = () => {
    if (currentStep === 2 && !canProceedFromStep2) {
      setAadhaarTouched(true);
      return;
    }
    if (currentStep < 4) {
      setCurrentStep(prev => prev + 1);
    } else {
      setSubmitted(true);
    }
  };

  const handleBack = () => {
    if (currentStep > 1) setCurrentStep(prev => prev - 1);
  };

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100 flex flex-col items-center justify-center p-4 md:p-8 font-sans">
      <div className="w-full max-w-4xl bg-slate-800/90 border border-slate-700/80 rounded-2xl shadow-2xl backdrop-blur-xl overflow-hidden flex flex-col">
        
        {/* Header Title Section */}
        <div className="p-6 md:p-8 border-b border-slate-700/80 bg-gradient-to-r from-slate-900 via-slate-800 to-slate-900">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="p-3 bg-indigo-600/20 rounded-xl border border-indigo-500/30 text-indigo-400">
                <ShieldCheck className="w-6 h-6" />
              </div>
              <div>
                <h1 className="text-xl md:text-2xl font-bold tracking-tight text-white">Regulatory Customer KYC</h1>
                <p className="text-xs md:text-sm text-slate-400">Aadhaar Identification & Real-time Bureau Assessment</p>
              </div>
            </div>
            <span className="hidden sm:inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              <Lock className="w-3 h-3" /> 256-Bit Encrypted
            </span>
          </div>

          {/* Multi-step progress bar */}
          <div className="mt-8 grid grid-cols-4 gap-2 md:gap-4">
            {STEPS.map((step) => {
              const StepIcon = step.icon;
              const isActive = currentStep === step.id;
              const isCompleted = currentStep > step.id;
              return (
                <div key={step.id} className="flex flex-col gap-2">
                  <div className="flex items-center gap-2">
                    <div
                      className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold transition-all duration-300 ${
                        isCompleted
                          ? 'bg-emerald-500 text-slate-950'
                          : isActive
                          ? 'bg-indigo-600 text-white ring-4 ring-indigo-500/20'
                          : 'bg-slate-700 text-slate-400'
                      }`}
                    >
                      {isCompleted ? <Check className="w-4 h-4 stroke-[3]" /> : <StepIcon className="w-4 h-4" />}
                    </div>
                    <span
                      className={`hidden md:inline text-xs font-medium truncate ${
                        isActive ? 'text-indigo-400 font-semibold' : isCompleted ? 'text-slate-200' : 'text-slate-500'
                      }`}
                    >
                      {step.name}
                    </span>
                  </div>
                  <div
                    className={`h-1.5 rounded-full transition-all duration-500 ${
                      isCompleted ? 'bg-emerald-500' : isActive ? 'bg-indigo-600' : 'bg-slate-700/60'
                    }`}
                  />
                </div>
              );
            })}
          </div>
        </div>

        {/* Main Content Area */}
        <div className="p-6 md:p-8 flex-1 min-h-[380px] bg-slate-800/40">
          {submitted ? (
            <motion.div 
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              className="flex flex-col items-center justify-center text-center py-12 space-y-4"
            >
              <div className="w-16 h-16 bg-emerald-500/20 border border-emerald-500/40 text-emerald-400 rounded-full flex items-center justify-center">
                <CheckCircle2 className="w-10 h-10" />
              </div>
              <h2 className="text-2xl font-bold text-white">KYC Verification Completed</h2>
              <p className="text-slate-400 max-w-md text-sm">
                Aadhaar identity <span className="text-slate-200 font-mono">({formatAadhaarDisplay(formData.aadhaar, true)})</span> and Credit Assessment have been processed and attached to the profile.
              </p>
              <button
                onClick={() => {
                  setSubmitted(false);
                  setCurrentStep(1);
                  setFormData(p => ({ ...p, aadhaar: '' }));
                  setAadhaarTouched(false);
                  setAadhaarValid(null);
                }}
                className="mt-4 px-6 py-2.5 bg-slate-700 hover:bg-slate-600 text-white rounded-xl text-sm font-semibold transition-colors"
              >
                Reset & Run Another Verification
              </button>
            </motion.div>
          ) : (
            <AnimatePresence mode="wait">
              <motion.div
                key={currentStep}
                initial={{ opacity: 0, x: 15 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -15 }}
                transition={{ duration: 0.2 }}
              >
                {/* Step 1: Personal Information */}
                {currentStep === 1 && (
                  <div className="space-y-4 max-w-xl mx-auto">
                    <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                      <User className="w-5 h-5 text-indigo-400" /> Primary Contact & Identity
                    </h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <label className="block text-xs font-medium text-slate-300 mb-1">Full Name (As per PAN)</label>
                        <input
                          type="text"
                          value={formData.fullName}
                          onChange={(e) => setFormData({ ...formData, fullName: e.target.value })}
                          className="w-full bg-slate-900/80 border border-slate-700 rounded-xl px-4 py-2.5 text-sm text-slate-100 focus:outline-none focus:border-indigo-500 transition-colors"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-slate-300 mb-1">Email Address</label>
                        <input
                          type="email"
                          value={formData.email}
                          onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                          className="w-full bg-slate-900/80 border border-slate-700 rounded-xl px-4 py-2.5 text-sm text-slate-100 focus:outline-none focus:border-indigo-500 transition-colors"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-slate-300 mb-1">Mobile Number</label>
                        <input
                          type="text"
                          value={formData.phone}
                          onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                          className="w-full bg-slate-900/80 border border-slate-700 rounded-xl px-4 py-2.5 text-sm text-slate-100 focus:outline-none focus:border-indigo-500 transition-colors"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-slate-300 mb-1">PAN Number</label>
                        <input
                          type="text"
                          value={formData.pan}
                          onChange={(e) => setFormData({ ...formData, pan: e.target.value.toUpperCase() })}
                          className="w-full bg-slate-900/80 border border-slate-700 rounded-xl px-4 py-2.5 text-sm text-slate-100 font-mono focus:outline-none focus:border-indigo-500 transition-colors uppercase"
                        />
                      </div>
                    </div>
                  </div>
                )}

                {/* Step 2: Aadhaar Input & Validation */}
                {currentStep === 2 && (
                  <div className="max-w-xl mx-auto space-y-6">
                    <div>
                      <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                        <ShieldCheck className="w-5 h-5 text-indigo-400" /> Aadhaar Card Verification
                      </h3>
                      <p className="text-xs text-slate-400 mt-1">
                        Enter the 12-digit unique identification number issued by UIDAI.
                      </p>
                    </div>

                    <div className="space-y-2">
                      <label className="block text-xs font-semibold uppercase tracking-wider text-slate-300">
                        Aadhaar Number <span className="text-rose-400">*</span>
                      </label>
                      
                      <div className="relative flex items-center">
                        <input
                          type={showAadhaar ? "text" : "password"}
                          value={formData.aadhaar}
                          onChange={handleAadhaarChange}
                          onBlur={handleAadhaarBlur}
                          maxLength={12}
                          placeholder="12 Digit Aadhaar Number"
                          className={`w-full bg-slate-900/90 border rounded-xl pl-4 pr-24 py-3 text-base font-mono tracking-widest text-slate-100 placeholder:text-slate-600 focus:outline-none transition-all ${
                            aadhaarTouched
                              ? aadhaarValid
                                ? 'border-emerald-500/80 focus:ring-2 focus:ring-emerald-500/20'
                                : 'border-rose-500 focus:ring-2 focus:ring-rose-500/20'
                              : 'border-slate-700 focus:border-indigo-500'
                          }`}
                        />
                        
                        {/* Action Icons Inside Input */}
                        <div className="absolute right-3 flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => setShowAadhaar(!showAadhaar)}
                            className="p-1.5 text-slate-400 hover:text-slate-200 transition-colors focus:outline-none rounded-lg hover:bg-slate-800"
                            title={showAadhaar ? "Mask Aadhaar" : "Unmask Aadhaar"}
                          >
                            {showAadhaar ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                          </button>

                          {aadhaarTouched && (
                            aadhaarValid ? (
                              <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                            ) : (
                              <AlertCircle className="w-5 h-5 text-rose-400" />
                            )
                          )}
                        </div>
                      </div>

                      {/* Formatted Preview Tag */}
                      {formData.aadhaar.length > 0 && (
                        <div className="flex items-center justify-between text-xs text-slate-400 px-1 pt-1 font-mono">
                          <span>Formatted Preview:</span>
                          <span className="font-bold text-indigo-300">
                            {formatAadhaarDisplay(formData.aadhaar, !showAadhaar)}
                          </span>
                        </div>
                      )}

                      {/* Real-time Inline Error Validation Message */}
                      {aadhaarTouched && !aadhaarValid && (
                        <motion.div
                          initial={{ opacity: 0, y: -4 }}
                          animate={{ opacity: 1, y: 0 }}
                          className="flex items-center gap-1.5 text-xs text-rose-400 pt-1 font-medium"
                        >
                          <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
                          <span>Invalid Aadhaar Number. Must contain exactly 12 numeric digits without symbols.</span>
                        </motion.div>
                      )}

                      {aadhaarTouched && aadhaarValid && (
                        <motion.div
                          initial={{ opacity: 0, y: -4 }}
                          animate={{ opacity: 1, y: 0 }}
                          className="flex items-center gap-1.5 text-xs text-emerald-400 pt-1 font-medium"
                        >
                          <CheckCircle2 className="w-3.5 h-3.5 flex-shrink-0" />
                          <span>Valid 12-digit Aadhaar format verified.</span>
                        </motion.div>
                      )}
                    </div>

                    <div className="bg-slate-900/40 border border-slate-700/50 rounded-xl p-4 flex gap-3 items-start text-xs text-slate-400">
                      <Info className="w-4 h-4 text-indigo-400 flex-shrink-0 mt-0.5" />
                      <span>
                        Aadhaar details are validated directly via UIDAI regulatory APIs. Information is stored in encrypted format in compliance with RBI KYC norms.
                      </span>
                    </div>
                  </div>
                )}

                {/* Step 3: Credit Score Gauge & Risk Metrics */}
                {currentStep === 3 && (
                  <div className="max-w-xl mx-auto space-y-6">
                    <div className="flex items-center justify-between">
                      <div>
                        <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                          <TrendingUp className="w-5 h-5 text-indigo-400" /> Calculated Credit Score
                        </h3>
                        <p className="text-xs text-slate-400 mt-0.5">
                          Automated lookup from Credit Information Bureau (CIBIL / Experian)
                        </p>
                      </div>

                      <button
                        onClick={refreshCreditScore}
                        disabled={isFetchingScore}
                        className="flex items-center gap-1.5 text-xs font-semibold px-3 py-2 bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-300 border border-indigo-500/30 rounded-xl transition-all disabled:opacity-50"
                      >
                        <RefreshCw className={`w-3.5 h-3.5 ${isFetchingScore ? 'animate-spin' : ''}`} />
                        Refresh Score
                      </button>
                    </div>

                    {creditScore !== null && (
                      <div className="bg-slate-900/90 border border-slate-700/80 rounded-2xl p-6 relative overflow-hidden">
                        {/* Top bar info */}
                        <div className="flex items-center justify-between pb-4 border-b border-slate-800 text-xs text-slate-400">
                          <span className="flex items-center gap-1.5">
                            <Building2 className="w-3.5 h-3.5 text-slate-500" /> Bureau: Experian / CIBIL
                          </span>
                          <span>Last synced: {lastUpdated}</span>
                        </div>

                        {/* Score Metric Visual Meter */}
                        <div className="py-6 flex flex-col items-center justify-center space-y-4">
                          {/* Circular/Linear Score Meter Display */}
                          <div className="relative flex flex-col items-center">
                            <div className="text-5xl font-extrabold text-white tracking-tight font-mono">
                              {isFetchingScore ? (
                                <span className="text-slate-600 animate-pulse">---</span>
                              ) : (
                                creditScore
                              )}
                            </div>
                            <div className="text-xs text-slate-400 mt-1">Score Range: 300 - 900</div>
                          </div>

                          {/* Risk Category Badge */}
                          {!isFetchingScore && (
                            <div className={`px-4 py-1.5 rounded-full border text-xs font-bold flex items-center gap-2 ${getRiskCategory(creditScore).bg}`}>
                              <span className={`w-2 h-2 rounded-full ${getRiskCategory(creditScore).barColor}`} />
                              <span className={getRiskCategory(creditScore).color}>
                                {getRiskCategory(creditScore).tier} Tier ({getRiskCategory(creditScore).label})
                              </span>
                            </div>
                          )}

                          {/* Custom Visual Linear Gauge Bar */}
                          <div className="w-full pt-2">
                            <div className="h-3 w-full bg-slate-800 rounded-full overflow-hidden p-0.5 border border-slate-700 relative">
                              <motion.div
                                initial={{ width: 0 }}
                                animate={{ width: isFetchingScore ? '0%' : getRiskCategory(creditScore).indicator }}
                                transition={{ duration: 0.8, ease: 'easeOut' }}
                                className={`h-full rounded-full ${getRiskCategory(creditScore).barColor}`}
                              />
                            </div>
                            <div className="flex justify-between text-[10px] text-slate-500 mt-1 font-mono">
                              <span>300 (Poor)</span>
                              <span>650 (Fair)</span>
                              <span>750 (Good)</span>
                              <span>900 (Excellent)</span>
                            </div>
                          </div>
                        </div>

                        {/* Read-Only Bureau Key Metrics Grid */}
                        <div className="grid grid-cols-3 gap-2 pt-4 border-t border-slate-800 text-center">
                          <div className="bg-slate-800/50 p-2.5 rounded-xl border border-slate-700/50">
                            <div className="text-[10px] text-slate-400 uppercase">On-Time Payments</div>
                            <div className="text-sm font-semibold text-emerald-400 mt-0.5">99.4%</div>
                          </div>
                          <div className="bg-slate-800/50 p-2.5 rounded-xl border border-slate-700/50">
                            <div className="text-[10px] text-slate-400 uppercase">Credit Utilization</div>
                            <div className="text-sm font-semibold text-indigo-400 mt-0.5">18%</div>
                          </div>
                          <div className="bg-slate-800/50 p-2.5 rounded-xl border border-slate-700/50">
                            <div className="text-[10px] text-slate-400 uppercase">Active Enquiries</div>
                            <div className="text-sm font-semibold text-amber-400 mt-0.5">1 Inquiry</div>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* Step 4: Final Summary Review */}
                {currentStep === 4 && (
                  <div className="max-w-xl mx-auto space-y-4">
                    <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                      <FileText className="w-5 h-5 text-indigo-400" /> Review KYC Summary
                    </h3>
                    
                    <div className="bg-slate-900/80 border border-slate-700/80 rounded-2xl divide-y divide-slate-800 text-xs">
                      <div className="p-4 flex justify-between items-center">
                        <span className="text-slate-400">Full Applicant Name</span>
                        <span className="font-semibold text-slate-200">{formData.fullName}</span>
                      </div>
                      <div className="p-4 flex justify-between items-center">
                        <span className="text-slate-400">PAN Number</span>
                        <span className="font-mono font-semibold text-slate-200">{formData.pan}</span>
                      </div>
                      <div className="p-4 flex justify-between items-center">
                        <span className="text-slate-400">Aadhaar Identification</span>
                        <span className="font-mono font-semibold text-emerald-400 flex items-center gap-1.5">
                          <CheckCircle2 className="w-3.5 h-3.5" />
                          {formatAadhaarDisplay(formData.aadhaar, !showAadhaar)}
                        </span>
                      </div>
                      <div className="p-4 flex justify-between items-center">
                        <span className="text-slate-400">Bureau Credit Score</span>
                        <span className="font-semibold text-indigo-300 bg-indigo-500/10 px-2.5 py-1 rounded-md border border-indigo-500/20">
                          {creditScore} ({creditScore ? getRiskCategory(creditScore).label : ''})
                        </span>
                      </div>
                    </div>
                  </div>
                )}
              </motion.div>
            </AnimatePresence>
          )}
        </div>

        {/* Navigation Controls Footer */}
        {!submitted && (
          <div className="p-4 md:p-6 border-t border-slate-700/80 bg-slate-900/60 flex items-center justify-between">
            <button
              onClick={handleBack}
              disabled={currentStep === 1}
              className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-slate-400 hover:text-white disabled:opacity-40 disabled:hover:text-slate-400 transition-colors"
            >
              <ArrowLeft className="w-4 h-4" /> Back
            </button>

            <div className="flex items-center gap-3">
              <button
                onClick={handleNext}
                className={`flex items-center gap-2 px-6 py-2.5 rounded-xl text-sm font-semibold transition-all shadow-lg ${
                  currentStep === 2 && !canProceedFromStep2
                    ? 'bg-slate-700 text-slate-400 cursor-not-allowed'
                    : 'bg-indigo-600 hover:bg-indigo-500 text-white shadow-indigo-600/20'
                }`}
              >
                {currentStep === 4 ? 'Submit Verification' : 'Continue'}
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}

      </div>
    </div>
  );
}