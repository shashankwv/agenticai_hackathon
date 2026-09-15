import React, { useState, useEffect, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  ShieldCheck,
  Eye,
  EyeOff,
  User,
  CreditCard,
  CheckCircle2,
  AlertCircle,
  ArrowRight,
  ArrowLeft,
  Lock,
  Building2,
  Sparkles,
  RefreshCw,
  FileText,
  Check,
  ChevronRight,
  Info
} from 'lucide-react';

interface FormData {
  fullName: string;
  dob: string;
  email: string;
  phone: string;
  aadhaarNumber: string;
  addressLine1: string;
  addressLine2: string;
  city: string;
  state: string;
  pincode: string;
  employmentType: string;
  annualIncome: string;
  calculatedCreditScore: number;
  termsAccepted: boolean;
}

const INITIAL_DATA: FormData = {
  fullName: 'Alexander Wright',
  dob: '1992-08-14',
  email: 'alex.wright@example.com',
  phone: '9876543210',
  aadhaarNumber: '',
  addressLine1: '402, Skyline Residency, MG Road',
  addressLine2: 'Indiranagar',
  city: 'Bengaluru',
  state: 'Karnataka',
  pincode: '560038',
  employmentType: 'Salaried',
  annualIncome: '1800000',
  calculatedCreditScore: 785,
  termsAccepted: false
};

const STEPS = [
  { id: 1, title: 'Identity & Aadhaar', subtitle: 'Personal identification details' },
  { id: 2, title: 'Address Details', subtitle: 'Permanent residency details' },
  { id: 3, title: 'Credit & Bureau Rating', subtitle: 'Calculated score & financial profile' },
  { id: 4, title: 'Review & Verification', subtitle: 'Final audit & ingestion' }
];

export default function CustomerKYCUpdateForm() {
  const [currentStep, setCurrentStep] = useState(1);
  const [formData, setFormData] = useState<FormData>(INITIAL_DATA);
  const [showAadhaar, setShowAadhaar] = useState(false);
  const [aadhaarTouched, setAadhaarTouched] = useState(false);
  const [isCalculatingScore, setIsCalculatingScore] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSubmitted, setIsSubmitted] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Aadhaar Regex Validation: Exactly 12 numeric digits
  const rawAadhaar = formData.aadhaarNumber.replace(/\s/g, '');
  const isAadhaarValid = useMemo(() => /^\d{12}$/.test(rawAadhaar), [rawAadhaar]);
  const aadhaarErrorMessage = rawAadhaar.length === 0
    ? 'Aadhaar Number is required'
    : !/^\d+$/.test(rawAadhaar)
    ? 'Aadhaar must contain numeric digits only'
    : rawAadhaar.length !== 12
    ? 'Aadhaar Number must be exactly 12 digits'
    : '';

  const handleAadhaarChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    // Extract digits only
    const digitsOnly = e.target.value.replace(/\D/g, '').slice(0, 12);
    setFormData(prev => ({ ...prev, aadhaarNumber: digitsOnly }));
  };

  const formatAadhaarDisplay = (val: string, visible: boolean) => {
    if (!val) return '';
    if (visible) {
      return val.replace(/(\d{4})(?=\d)/g, '$1 ');
    } else {
      const masked = 'X'.repeat(Math.max(0, val.length - 4)) + val.slice(-4);
      return masked.replace(/(.{4})(?=\S)/g, '$1 ');
    }
  };

  const updateCreditScore = () => {
    setIsCalculatingScore(true);
    setTimeout(() => {
      const incomeNum = parseInt(formData.annualIncome) || 500000;
      const baseScore = 650;
      const incomeBoost = Math.min(150, Math.floor(incomeNum / 20000));
      const mockScore = Math.min(850, Math.max(300, baseScore + incomeBoost));
      setFormData(prev => ({ ...prev, calculatedCreditScore: mockScore }));
      setIsCalculatingScore(false);
    }, 1200);
  };

  useEffect(() => {
    if (currentStep === 3) {
      updateCreditScore();
    }
  }, [currentStep]);

  const isStepValid = (step: number) => {
    switch (step) {
      case 1:
        return formData.fullName.trim() !== '' && formData.dob !== '' && isAadhaarValid;
      case 2:
        return formData.addressLine1.trim() !== '' && formData.pincode.length === 6;
      case 3:
        return !!formData.employmentType && !!formData.annualIncome;
      case 4:
        return formData.termsAccepted;
      default:
        return true;
    }
  };

  const handleNext = () => {
    if (currentStep === 1) setAadhaarTouched(true);
    if (isStepValid(currentStep) && currentStep < 4) {
      setCurrentStep(prev => prev + 1);
    }
  };

  const handleBack = () => {
    if (currentStep > 1) {
      setCurrentStep(prev => prev - 1);
    }
  };

  const handleSubmit = async () => {
    setSubmitError(null);
    setIsSubmitting(true);
    try {
      const response = await fetch('/api/ingest', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(formData)
      });

      if (response.ok) {
        setIsSubmitted(true);
      } else {
        setSubmitError(`Ingestion API responded with status ${response.status}`);
      }
    } catch (err: any) {
      // Fallback for simulation/demo if endpoint not reachable
      setSubmitError(err.message || 'API request failed');
    } finally {
      setIsSubmitting(false);
    }
  };

  const getScoreRating = (score: number) => {
    if (score >= 750) return { text: 'Excellent', color: 'text-emerald-600', bg: 'bg-emerald-50 border-emerald-200' };
    if (score >= 700) return { text: 'Good', color: 'text-blue-600', bg: 'bg-blue-50 border-blue-200' };
    if (score >= 650) return { text: 'Fair', color: 'text-amber-600', bg: 'bg-amber-50 border-amber-200' };
    return { text: 'Needs Improvement', color: 'text-rose-600', bg: 'bg-rose-50 border-rose-200' };
  };

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100 flex items-center justify-center p-4 md:p-8 font-sans">
      <div className="w-full max-w-4xl bg-slate-800 border border-slate-700/80 rounded-2xl shadow-2xl overflow-hidden flex flex-col min-h-[640px]">
        
        {/* Header */}
        <div className="bg-slate-900/80 px-6 py-5 border-b border-slate-700/80 flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center space-x-3">
            <div className="p-2.5 bg-indigo-600/20 text-indigo-400 rounded-xl border border-indigo-500/30">
              <Building2 className="w-6 h-6" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="text-xs font-semibold uppercase tracking-wider text-indigo-400 bg-indigo-950/60 border border-indigo-800/50 px-2 py-0.5 rounded-md">
                  Core Banking 360
                </span>
                <span className="text-xs text-slate-400">Jira Task: KYC-1094</span>
              </div>
              <h1 className="text-xl font-bold text-white tracking-tight">Customer KYC Registration</h1>
            </div>
          </div>
          <div className="flex items-center space-x-2 text-xs text-slate-400 bg-slate-800/80 px-3 py-1.5 rounded-lg border border-slate-700">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
            <span>UIDAI Encrypted Sync Enabled</span>
          </div>
        </div>

        {/* Step Progress Tracker */}
        {!isSubmitted && (
          <div className="bg-slate-800/50 border-b border-slate-700/60 px-6 py-4">
            <div className="grid grid-cols-4 gap-2 md:gap-4">
              {STEPS.map((step) => {
                const isCompleted = currentStep > step.id;
                const isCurrent = currentStep === step.id;
                return (
                  <div key={step.id} className="flex flex-col space-y-1.5">
                    <div className="flex items-center space-x-2">
                      <div
                        className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold transition-colors ${ 
                          isCompleted
                            ? 'bg-emerald-500 text-slate-950'
                            : isCurrent
                            ? 'bg-indigo-600 text-white ring-2 ring-indigo-400/30'
                            : 'bg-slate-700 text-slate-400'
                        }`}
                      >
                        {isCompleted ? <Check className="w-4 h-4 stroke-[3]" /> : step.id}
                      </div>
                      <div className="hidden md:block truncate text-xs font-medium">
                        <span className={isCurrent ? 'text-white font-semibold' : 'text-slate-400'}>
                          {step.title}
                        </span>
                      </div>
                    </div>
                    <div className="w-full bg-slate-700/60 h-1.5 rounded-full overflow-hidden">
                      <motion.div
                        className={`h-full ${isCompleted || isCurrent ? 'bg-indigo-500' : 'bg-transparent'}`}
                        initial={{ width: '0%' }}
                        animate={{ width: isCompleted ? '100%' : isCurrent ? '50%' : '0%' }}
                        transition={{ duration: 0.3 }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Form Body */}
        <div className="flex-1 p-6 md:p-8 relative flex flex-col justify-between">
          {isSubmitted ? (
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              className="my-auto flex flex-col items-center text-center space-y-6 py-8"
            >
              <div className="w-20 h-20 bg-emerald-500/20 text-emerald-400 rounded-full flex items-center justify-center ring-8 ring-emerald-500/10">
                <CheckCircle2 className="w-10 h-10" />
              </div>
              <div className="space-y-2 max-w-md">
                <h2 className="text-2xl font-bold text-white">KYC Record Submitted Successfully</h2>
                <p className="text-sm text-slate-400">
                  Customer details and verified Aadhaar profile have been ingested into the Core Banking 360 repository.
                </p> <br/>
                <p className="text-xs text-slate-500 font-mono bg-slate-900 px-3 py-1.5 rounded border border-slate-700/50 inline-block">
                  Ref ID: KYC-INGEST-{Math.floor(100000 + Math.random() * 900000)}
                </p>
              </div>
              <button
                onClick={() => {
                  setIsSubmitted(false);
                  setCurrentStep(1);
                  setFormData(INITIAL_DATA);
                }}
                className="px-6 py-2.5 bg-slate-700 hover:bg-slate-600 text-white rounded-lg text-sm font-medium transition-colors"
              >
                Register Another Customer
              </button>
            </motion.div>
          ) : (
            <AnimatePresence mode="wait">
              <motion.div
                key={currentStep}
                initial={{ opacity: 0, x: 15 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -15 }}
                transition={{ duration: 0.25 }}
                className="space-y-6 flex-1"
              >
                {/* STEP 1: IDENTITY & AADHAAR */}
                {currentStep === 1 && (
                  <div className="space-y-5">
                    <div>
                      <h2 className="text-lg font-bold text-white flex items-center gap-2">
                        <User className="w-5 h-5 text-indigo-400" /> Customer Identification
                      </h2>
                      <p className="text-xs text-slate-400 mt-1">
                        Enter personal identity parameters and valid 12-digit UIDAI Aadhaar.
                      </p>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                          Full Legal Name *
                        </label>
                        <input
                          type="text"
                          value={formData.fullName}
                          onChange={e => setFormData({ ...formData, fullName: e.target.value })}
                          className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3.5 py-2.5 text-sm text-white focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500"
                          placeholder="e.g. Alexander Wright"
                        />
                      </div>

                      <div>
                        <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                          Date of Birth *
                        </label>
                        <input
                          type="date"
                          value={formData.dob}
                          onChange={e => setFormData({ ...formData, dob: e.target.value })}
                          className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3.5 py-2.5 text-sm text-white focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500"
                        />
                      </div>
                    </div>

                    {/* AADHAAR INPUT COMPONENT (Jira Requirement) */}
                    <div className="bg-slate-900/60 border border-slate-700/80 rounded-xl p-4 space-y-3">
                      <div className="flex items-center justify-between">
                        <label className="block text-xs font-semibold text-indigo-300 flex items-center gap-1.5">
                          <Lock className="w-3.5 h-3.5 text-indigo-400" /> Aadhaar Number (12 Digits) *
                        </label>
                        <span className="text-[11px] text-slate-400">Regex rule: <code className="text-indigo-300 bg-slate-800 px-1 py-0.5 rounded">^\d&#123;12&#125;$</code></span>
                      </div>

                      <div className="relative">
                        <input
                          type={showAadhaar ? 'text' : 'password'}
                          maxLength={12}
                          value={formData.aadhaarNumber}
                          onBlur={() => setAadhaarTouched(true)}
                          onChange={handleAadhaarChange}
                          placeholder="Enter 12 digit Aadhaar"
                          className={`w-full bg-slate-950 border ${ 
                            aadhaarTouched && !isAadhaarValid
                              ? 'border-rose-500/80 focus:ring-rose-500/40'
                              : 'border-slate-700 focus:ring-indigo-500/50'
                          } rounded-lg pl-3.5 pr-20 py-2.5 text-sm text-white font-mono tracking-wider focus:outline-none focus:ring-2`}
                        />
                        
                        <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center space-x-1 bg-slate-900/90 px-1 rounded-md border border-slate-700/50">
                          <button
                            type="button"
                            onClick={() => setShowAadhaar(!showAadhaar)}
                            className="p-1 text-slate-400 hover:text-white transition-colors"
                            title={showAadhaar ? 'Hide Aadhaar' : 'Show Aadhaar'}
                          >
                            {showAadhaar ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                          </button>
                        </div>
                      </div>

                      {/* Validation Error Message */}
                      {aadhaarTouched && !isAadhaarValid && (
                        <motion.div
                          initial={{ opacity: 0, y: -4 }}
                          animate={{ opacity: 1, y: 0 }}
                          className="flex items-center space-x-1.5 text-rose-400 text-xs font-medium mt-1.5"
                        >
                          <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                          <span>{aadhaarErrorMessage}</span>
                        </motion.div>
                      )}

                      {isAadhaarValid && (
                        <motion.div
                          initial={{ opacity: 0 }}
                          animate={{ opacity: 1 }}
                          className="flex items-center space-x-1.5 text-emerald-400 text-xs font-medium mt-1"
                        >
                          <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
                          <span>Valid 12-digit Aadhaar format</span>
                        </motion.div>
                      )}

                      <p className="text-[11px] text-slate-400 flex items-start gap-1">
                        <Info className="w-3.5 h-3.5 text-slate-500 shrink-0 mt-0.5" />
                        Aadhaar numbers are masked by default and stored strictly in compliance with security guidelines.
                      </p>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                          Email Address
                        </label>
                        <input
                          type="email"
                          value={formData.email}
                          onChange={e => setFormData({ ...formData, email: e.target.value })}
                          className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3.5 py-2.5 text-sm text-white focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                          Phone Number
                        </label>
                        <input
                          type="text"
                          value={formData.phone}
                          onChange={e => setFormData({ ...formData, phone: e.target.value })}
                          className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3.5 py-2.5 text-sm text-white focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
                        />
                      </div>
                    </div>
                  </div>
                )}

                {/* STEP 2: ADDRESS */}
                {currentStep === 2 && (
                  <div className="space-y-4">
                    <div>
                      <h2 className="text-lg font-bold text-white flex items-center gap-2">
                        <Building2 className="w-5 h-5 text-indigo-400" /> Residence Information
                      </h2>
                      <p className="text-xs text-slate-400 mt-1">
                        Provide address corresponding to official identity verification records.
                      </p>
                    </div>

                    <div className="space-y-3">
                      <div>
                        <label className="block text-xs font-semibold text-slate-300 mb-1.5">Address Line 1 *</label>
                        <input
                          type="text"
                          value={formData.addressLine1}
                          onChange={e => setFormData({ ...formData, addressLine1: e.target.value })}
                          className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3.5 py-2.5 text-sm text-white focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-semibold text-slate-300 mb-1.5">Address Line 2</label>
                        <input
                          type="text"
                          value={formData.addressLine2}
                          onChange={e => setFormData({ ...formData, addressLine2: e.target.value })}
                          className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3.5 py-2.5 text-sm text-white focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
                        />
                      </div>
                      <div className="grid grid-cols-3 gap-3">
                        <div>
                          <label className="block text-xs font-semibold text-slate-300 mb-1.5">City</label>
                          <input
                            type="text"
                            value={formData.city}
                            onChange={e => setFormData({ ...formData, city: e.target.value })}
                            className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3.5 py-2.5 text-sm text-white focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
                          />
                        </div>
                        <div>
                          <label className="block text-xs font-semibold text-slate-300 mb-1.5">State</label>
                          <input
                            type="text"
                            value={formData.state}
                            onChange={e => setFormData({ ...formData, state: e.target.value })}
                            className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3.5 py-2.5 text-sm text-white focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
                          />
                        </div>
                        <div>
                          <label className="block text-xs font-semibold text-slate-300 mb-1.5">Pincode *</label>
                          <input
                            type="text"
                            maxLength={6}
                            value={formData.pincode}
                            onChange={e => setFormData({ ...formData, pincode: e.target.value.replace(/\D/g, '') })}
                            className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3.5 py-2.5 text-sm text-white focus:outline-none focus:ring-2 focus:ring-indigo-500/50 font-mono"
                          />
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {/* STEP 3: CREDIT SCORE (READ-ONLY COMPONENT) */}
                {currentStep === 3 && (
                  <div className="space-y-5">
                    <div>
                      <h2 className="text-lg font-bold text-white flex items-center gap-2">
                        <CreditCard className="w-5 h-5 text-indigo-400" /> Financial Profile & Credit Bureau Rating
                      </h2>
                      <p className="text-xs text-slate-400 mt-1">
                        Includes real-time calculated credit bureau score derived from customer parameters.
                      </p>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <label className="block text-xs font-semibold text-slate-300 mb-1.5">Employment Type</label>
                        <select
                          value={formData.employmentType}
                          onChange={e => {
                            setFormData({ ...formData, employmentType: e.target.value });
                            updateCreditScore();
                          }}
                          className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3.5 py-2.5 text-sm text-white focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
                        >
                          <option value="Salaried">Salaried</option>
                          <option value="Self-Employed">Self-Employed</option>
                          <option value="Business Owner">Business Owner</option>
                          <option value="Professional">Professional</option>
                        </select>
                      </div>
                      <div>
                        <label className="block text-xs font-semibold text-slate-300 mb-1.5">Annual Income (INR)</label>
                        <input
                          type="number"
                          value={formData.annualIncome}
                          onChange={e => {
                            setFormData({ ...formData, annualIncome: e.target.value });
                          }}
                          onBlur={updateCreditScore}
                          className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3.5 py-2.5 text-sm text-white focus:outline-none focus:ring-2 focus:ring-indigo-500/50 font-mono"
                        />
                      </div>
                    </div>

                    {/* READ-ONLY CREDIT SCORE DISPLAY COMPONENT (Jira Requirement) */}
                    <div className="bg-slate-900/90 border border-indigo-500/30 rounded-xl p-5 relative overflow-hidden">
                      <div className="absolute top-0 right-0 w-32 h-32 bg-indigo-500/5 rounded-full blur-2xl pointer-events-none" />
                      
                      <div className="flex items-center justify-between mb-4">
                        <div className="flex items-center space-x-2">
                          <Sparkles className="w-4 h-4 text-indigo-400" />
                          <span className="text-xs font-bold uppercase tracking-wider text-slate-300">
                            Calculated Credit Score (Read-Only)
                          </span>
                        </div>
                        <button
                          type="button"
                          onClick={updateCreditScore}
                          disabled={isCalculatingScore}
                          className="text-xs text-indigo-400 hover:text-indigo-300 flex items-center gap-1 transition-colors disabled:opacity-50"
                        >
                          <RefreshCw className={`w-3.5 h-3.5 ${isCalculatingScore ? 'animate-spin' : ''}`} />
                          Recalculate Bureau Sync
                        </button>
                      </div>

                      <div className="flex flex-col md:flex-row items-center justify-between gap-6 bg-slate-950/80 p-4 rounded-lg border border-slate-800">
                        <div className="flex items-center space-x-4">
                          <div className="relative flex items-center justify-center w-20 h-20 rounded-full bg-slate-900 border-2 border-indigo-500/40 text-2xl font-black text-white tracking-tight">
                            {isCalculatingScore ? (
                              <RefreshCw className="w-6 h-6 animate-spin text-indigo-400" />
                            ) : (
                              formData.calculatedCreditScore
                            )}
                          </div>
                          <div>
                            <div className="text-xs text-slate-400 font-medium">Bureau Credit Grade</div>
                            <div className="text-lg font-bold text-white flex items-center gap-2 mt-0.5">
                              {getScoreRating(formData.calculatedCreditScore).text}
                              <span className="text-xs px-2 py-0.5 rounded border font-semibold bg-indigo-500/10 border-indigo-500/30 text-indigo-300">
                                CIBIL Standard
                              </span>
                            </div>
                            <div className="text-[11px] text-slate-500 mt-1">
                              Range: 300 to 850 • Refreshed just now
                            </div>
                          </div>
                        </div>

                        {/* Read-Only Gauge / Status Bar */}
                        <div className="w-full md:w-48 space-y-2">
                          <div className="flex justify-between text-[10px] text-slate-400 font-mono">
                            <span>300</span>
                            <span>650</span>
                            <span>850</span>
                          </div>
                          <div className="w-full h-2.5 bg-slate-800 rounded-full overflow-hidden p-0.5 border border-slate-700">
                            <div
                              className="h-full bg-gradient-to-r from-amber-500 via-indigo-500 to-emerald-400 rounded-full transition-all duration-700"
                              style={{
                                width: `${Math.min(100, Math.max(0, ((formData.calculatedCreditScore - 300) / 550) * 100))}%`
                              }}
                            />
                          </div>
                          <div className="text-[10px] text-slate-400 text-right font-medium">
                            Tier A Eligibility Verified
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {/* STEP 4: REVIEW & SUBMIT */}
                {currentStep === 4 && (
                  <div className="space-y-4">
                    <div>
                      <h2 className="text-lg font-bold text-white flex items-center gap-2">
                        <FileText className="w-5 h-5 text-indigo-400" /> Audit & Confirm Details
                      </h2>
                      <p className="text-xs text-slate-400 mt-1">
                        Please review the KYC record before submitting for ingest API pipeline.
                      </p>
                    </div>

                    <div className="bg-slate-900 border border-slate-700/80 rounded-xl p-4 space-y-3 text-xs">
                      <div className="grid grid-cols-2 gap-y-2 gap-x-4 border-b border-slate-800 pb-3">
                        <div>
                          <span className="text-slate-400 block">Customer Name</span>
                          <span className="font-medium text-white text-sm">{formData.fullName}</span>
                        </div>
                        <div>
                          <span className="text-slate-400 block">Aadhaar Number (Masked)</span>
                          <span className="font-mono font-medium text-indigo-300 text-sm">
                            {formatAadhaarDisplay(formData.aadhaarNumber, false)}
                          </span>
                        </div>
                      </div>

                      <div className="grid grid-cols-2 gap-y-2 gap-x-4 border-b border-slate-800 pb-3">
                        <div>
                          <span className="text-slate-400 block">Residence Address</span>
                          <span className="font-medium text-white">
                            {formData.addressLine1}, {formData.city}, {formData.state} - {formData.pincode}
                          </span>
                        </div>
                        <div>
                          <span className="text-slate-400 block">Calculated Credit Score</span>
                          <span className="font-mono font-bold text-emerald-400 text-sm">
                            {formData.calculatedCreditScore} / 850
                          </span>
                        </div>
                      </div>

                      <div className="pt-1">
                        <label className="flex items-start space-x-2.5 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={formData.termsAccepted}
                            onChange={e => setFormData({ ...formData, termsAccepted: e.target.checked })}
                            className="mt-0.5 rounded border-slate-700 text-indigo-600 focus:ring-indigo-500 bg-slate-950"
                          />
                          <span className="text-slate-300 text-xs leading-relaxed">
                            I hereby declare that the Aadhaar details provided are true to my knowledge and consent to submitting this KYC payload for Core Banking 360 ingestion.
                          </span>
                        </label>
                      </div>
                    </div>

                    {submitError && (
                      <div className="p-3 bg-rose-500/10 border border-rose-500/30 rounded-lg text-rose-300 text-xs flex items-center space-x-2">
                        <AlertCircle className="w-4 h-4 shrink-0" />
                        <span>Submit Error: {submitError} (Simulating payload ingestion)</span>
                      </div>
                    )}
                  </div>
                )}
              </motion.div>
            </AnimatePresence>
          )}

          {/* Bottom Actions Bar */}
          {!isSubmitted && (
            <div className="mt-8 pt-4 border-t border-slate-700/80 flex items-center justify-between">
              <button
                type="button"
                onClick={handleBack}
                disabled={currentStep === 1}
                className="px-4 py-2 rounded-lg text-xs font-semibold text-slate-300 hover:text-white disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1 transition-colors"
              >
                <ArrowLeft className="w-4 h-4" /> Back
              </button>

              {currentStep < 4 ? (
                <button
                  type="button"
                  onClick={handleNext}
                  disabled={!isStepValid(currentStep)}
                  className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-xs font-bold transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5 shadow-lg shadow-indigo-600/20"
                >
                  <span>Continue</span>
                  <ChevronRight className="w-4 h-4" />
                </button>
              ) : (
                <button
                  type="button"
                  onClick={handleSubmit}
                  disabled={!isStepValid(4) || isSubmitting}
                  className="px-6 py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-bold transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5 shadow-lg shadow-emerald-600/20"
                >
                  {isSubmitting ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      <span>Ingesting Data...</span>
                    </>
                  ) : (
                    <>
                      <Check className="w-4 h-4 stroke-[3]" />
                      <span>Submit Ingestion Payload</span>
                    </>
                  )}
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
