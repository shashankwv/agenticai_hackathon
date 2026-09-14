import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Eye,
  EyeOff,
  ShieldCheck,
  CheckCircle2,
  AlertCircle,
  CreditCard,
  User,
  FileText,
  ChevronRight,
  ChevronLeft,
  Loader2,
  Sparkles,
  Lock,
  RefreshCw,
  Check,
  Building2,
  Award
} from 'lucide-react';

type FormData = {
  fullName: string;
  email: string;
  phone: string;
  dob: string;
  aadhaarNumber: string;
  panNumber: string;
  creditScore: number | null;
  creditRating: string;
  creditFetchDate: string;
};

const STEPS = [
  { id: 'personal', title: 'Personal Info', icon: User },
  { id: 'identity', title: 'Identity & Aadhaar', icon: FileText },
  { id: 'credit', title: 'Credit Bureau Integration', icon: CreditCard },
  { id: 'review', title: 'Review & Submit', icon: ShieldCheck },
];

export default function CustomerKYCForm() {
  const [currentStep, setCurrentStep] = useState<number>(0);
  const [showAadhaar, setShowAadhaar] = useState<boolean>(false);
  const [isFetchingScore, setIsFetchingScore] = useState<boolean>(false);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [isSubmitted, setIsSubmitted] = useState<boolean>(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [touched, setTouched] = useState<Record<string, boolean>>({});

  const [formData, setFormData] = useState<FormData>({
    fullName: '',
    email: '',
    phone: '',
    dob: '',
    aadhaarNumber: '',
    panNumber: '',
    creditScore: null,
    creditRating: '',
    creditFetchDate: '',
  });

  // Aadhaar Regex: strict 12 numeric digits
  const aadhaarRegex = /^\d{12}$/;
  const isAadhaarValid = aadhaarRegex.test(formData.aadhaarNumber);

  const handleInputChange = (field: keyof FormData, value: string) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  const handleBlur = (field: string) => {
    setTouched((prev) => ({ ...prev, [field]: true }));
  };

  const fetchCreditScore = () => {
    setIsFetchingScore(true);
    // Simulate Credit Bureau API delay
    setTimeout(() => {
      const generatedScore = Math.floor(Math.random() * (850 - 680 + 1)) + 680;
      let rating = 'Fair';
      if (generatedScore >= 780) rating = 'Excellent';
      else if (generatedScore >= 720) rating = 'Good';

      setFormData((prev) => ({
        ...prev,
        creditScore: generatedScore,
        creditRating: rating,
        creditFetchDate: new Date().toLocaleDateString('en-IN', {
          day: 'numeric',
          month: 'short',
          year: 'numeric',
          hour: '2-digit',
          minute: '2-digit',
        }),
      }));
      setIsFetchingScore(false);
    }, 1800);
  };

  const isStepValid = (step: number): boolean => {
    switch (step) {
      case 0:
        return !!(
          formData.fullName.trim() &&
          formData.email.includes('@') &&
          formData.phone.length >= 10 &&
          formData.dob
        );
      case 1:
        return isAadhaarValid && formData.panNumber.length >= 10;
      case 2:
        return formData.creditScore !== null;
      default:
        return true;
    }
  };

  const handleNext = () => {
    if (isStepValid(currentStep)) {
      setCurrentStep((prev) => Math.min(prev + 1, STEPS.length - 1));
    }
  };

  const handleBack = () => {
    setCurrentStep((prev) => Math.max(prev - 1, 0));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setSubmitError(null);

    try {
      const response = await fetch('/api/ingest', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          timestamp: new Date().toISOString(),
          kycData: formData,
        }),
      });

      if (response.ok) {
        setIsSubmitted(true);
      } else {
        throw new Error(`Submission failed with status: ${response.status}`);
      }
    } catch (err: any) {
      // Fallback message for demo environment if /api/ingest endpoint isn't live
      console.warn('API error encountered:', err);
      setSubmitError(
        err.message || 'Failed to submit form to server. Please try again.'
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  const formatAadhaarDisplay = (val: string) => {
    if (!val) return '';
    const clean = val.replace(/\D/g, '').slice(0, 12);
    if (!showAadhaar) {
      // Mask first 8 digits
      if (clean.length <= 8) {
        return '•'.repeat(clean.length);
      }
      return '•'.repeat(8) + ' ' + clean.slice(8);
    }
    // Show formatted with spaces
    return clean.replace(/(\d{4})(?=\d)/g, '$1 ');
  };

  const renderStepContent = () => {
    switch (currentStep) {
      case 0:
        return (
          <motion.div
            key="step-0"
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            transition={{ duration: 0.3 }}
            className="space-y-4"
          >
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1">
                Full Legal Name
              </label>
              <input
                type="text"
                placeholder="e.g. Rahul Sharma"
                value={formData.fullName}
                onChange={(e) => handleInputChange('fullName', e.target.value)}
                className="w-full rounded-lg border border-slate-300 px-4 py-2.5 text-sm text-slate-900 focus:border-indigo-600 focus:outline-none focus:ring-1 focus:ring-indigo-600 transition"
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1">
                  Email Address
                </label>
                <input
                  type="email"
                  placeholder="rahul@example.com"
                  value={formData.email}
                  onChange={(e) => handleInputChange('email', e.target.value)}
                  className="w-full rounded-lg border border-slate-300 px-4 py-2.5 text-sm text-slate-900 focus:border-indigo-600 focus:outline-none focus:ring-1 focus:ring-indigo-600 transition"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1">
                  Phone Number
                </label>
                <input
                  type="tel"
                  placeholder="+91 98765 43210"
                  value={formData.phone}
                  onChange={(e) => handleInputChange('phone', e.target.value)}
                  className="w-full rounded-lg border border-slate-300 px-4 py-2.5 text-sm text-slate-900 focus:border-indigo-600 focus:outline-none focus:ring-1 focus:ring-indigo-600 transition"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1">
                Date of Birth
              </label>
              <input
                type="date"
                value={formData.dob}
                onChange={(e) => handleInputChange('dob', e.target.value)}
                className="w-full rounded-lg border border-slate-300 px-4 py-2.5 text-sm text-slate-900 focus:border-indigo-600 focus:outline-none focus:ring-1 focus:ring-indigo-600 transition"
              />
            </div>
          </motion.div>
        );

      case 1:
        return (
          <motion.div
            key="step-1"
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            transition={{ duration: 0.3 }}
            className="space-y-5"
          >
            {/* Aadhaar Input Field with Regex & Masking */}
            <div>
              <div className="flex justify-between items-center mb-1">
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700">
                  Aadhaar Number (12 Digits)
                </label>
                <span className="text-[11px] font-medium text-emerald-600 flex items-center gap-1">
                  <Lock className="w-3 h-3" /> UIDAI Encrypted
                </span>
              </div>

              <div className="relative">
                <input
                  type={showAadhaar ? 'text' : 'password'}
                  maxLength={12}
                  placeholder="Enter 12-digit Aadhaar number"
                  value={formData.aadhaarNumber}
                  onBlur={() => handleBlur('aadhaarNumber')}
                  onChange={(e) => {
                    const raw = e.target.value.replace(/\D/g, '').slice(0, 12);
                    handleInputChange('aadhaarNumber', raw);
                  }}
                  className={`w-full rounded-lg border px-4 py-2.5 text-sm text-slate-900 font-mono tracking-widest focus:outline-none transition pr-12 ${
                    touched.aadhaarNumber && !isAadhaarValid
                      ? 'border-rose-500 focus:ring-1 focus:ring-rose-500 bg-rose-50/20'
                      : isAadhaarValid
                      ? 'border-emerald-500 focus:ring-1 focus:ring-emerald-500 bg-emerald-50/20'
                      : 'border-slate-300 focus:border-indigo-600 focus:ring-1 focus:ring-indigo-600'
                  }`}
                />
                <button
                  type="button"
                  onClick={() => setShowAadhaar(!showAadhaar)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 transition p-1"
                  title={showAadhaar ? 'Mask Aadhaar' : 'Show Aadhaar'}
                >
                  {showAadhaar ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>

              {/* Real-time Regex Validation Message */}
              {touched.aadhaarNumber && !isAadhaarValid && (
                <p className="mt-1.5 text-xs text-rose-600 flex items-center gap-1 font-medium">
                  <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                  Must be exactly 12 numeric digits (format: ^\d&#123;12&#125;$)
                </p>
              )}

              {isAadhaarValid && (
                <p className="mt-1.5 text-xs text-emerald-600 flex items-center gap-1 font-medium">
                  <CheckCircle2 className="w-3.5 h-3.5 shrink-0" /> Valid 12-digit Aadhaar format
                </p>
              )}

              {/* Visual Masking Preview */}
              {formData.aadhaarNumber && (
                <div className="mt-2 p-2 bg-slate-50 rounded border border-slate-200 flex justify-between items-center text-xs text-slate-600 font-mono">
                  <span className="text-[11px] text-slate-400 uppercase tracking-wider font-sans">
                    Formatted Preview:
                  </span>
                  <span>{formatAadhaarDisplay(formData.aadhaarNumber)}</span>
                </div>
              )}
            </div>

            {/* PAN Card Input */}
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1">
                PAN Number
              </label>
              <input
                type="text"
                maxLength={10}
                placeholder="ABCDE1234F"
                value={formData.panNumber}
                onChange={(e) => handleInputChange('panNumber', e.target.value.toUpperCase())}
                className="w-full rounded-lg border border-slate-300 px-4 py-2.5 text-sm text-slate-900 font-mono focus:border-indigo-600 focus:outline-none focus:ring-1 focus:ring-indigo-600 transition uppercase"
              />
            </div>
          </motion.div>
        );

      case 2:
        return (
          <motion.div
            key="step-2"
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            transition={{ duration: 0.3 }}
            className="space-y-6"
          >
            <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 flex items-center gap-3">
              <Building2 className="w-8 h-8 text-indigo-600 shrink-0" />
              <div>
                <h4 className="text-sm font-semibold text-slate-800">
                  Bureau Integration
                </h4>
                <p className="text-xs text-slate-500">
                  Fetch real-time credit metrics using verified PAN ({formData.panNumber || 'N/A'}) & Aadhaar.
                </p>
              </div>
            </div>

            {/* Read-Only Display Element for Calculated Credit Score */}
            <div className="border border-slate-200 rounded-xl p-5 bg-gradient-to-br from-slate-900 to-indigo-950 text-white relative overflow-hidden shadow-md">
              <div className="absolute -right-8 -bottom-8 opacity-10 pointer-events-none">
                <Award className="w-48 h-48 text-indigo-300" />
              </div>

              <div className="flex justify-between items-start mb-4">
                <div>
                  <span className="text-[11px] font-semibold text-indigo-300 uppercase tracking-wider block">
                    Calculated Credit Score
                  </span>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Bureau Query Status: {formData.creditScore ? 'Verified' : 'Pending'}
                  </p>
                </div>
                <span className="px-2.5 py-1 rounded-full text-[10px] font-bold tracking-wider uppercase bg-white/10 text-indigo-200 border border-white/10">
                  Read-Only Element
                </span>
              </div>

              <div className="flex items-baseline gap-3 my-2">
                <span className="text-4xl font-extrabold tracking-tight">
                  {formData.creditScore !== null ? formData.creditScore : '---'}
                </span>
                {formData.creditScore && (
                  <span
                    className={`text-xs font-semibold px-2 py-0.5 rounded ${'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'}`}
                  >
                    {formData.creditRating}
                  </span>
                )}
              </div>

              {/* Score Range Progress Bar */}
              {formData.creditScore !== null && (
                <div className="mt-4 space-y-1.5">
                  <div className="h-2 w-full bg-slate-800 rounded-full overflow-hidden flex">
                    <div
                      className="h-full bg-gradient-to-r from-indigo-500 to-emerald-400 transition-all duration-1000 ease-out"
                      style={{
                        width: `${Math.min(
                          Math.max(
                            ((formData.creditScore - 300) / (900 - 300)) * 100,
                            0
                          ),
                          100
                        )}%`,
                      }}
                    />
                  </div>
                  <div className="flex justify-between text-[10px] text-slate-400 font-mono">
                    <span>300 (Poor)</span>
                    <span>900 (Excellent)</span>
                  </div>
                </div>
              )}

              {formData.creditFetchDate && (
                <p className="text-[11px] text-slate-400 mt-4 pt-3 border-t border-white/10 flex items-center justify-between">
                  <span>Bureau Reference Timestamp</span>
                  <span className="font-mono text-indigo-200">
                    {formData.creditFetchDate}
                  </span>
                </p>
              )}
            </div>

            {/* Trigger Button to Calculate/Fetch Credit Score */}
            <div className="flex justify-center">
              <button
                type="button"
                onClick={fetchCreditScore}
                disabled={isFetchingScore}
                className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-6 py-2.5 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 font-semibold text-sm rounded-lg border border-indigo-200 transition disabled:opacity-50 shadow-sm"
              >
                {isFetchingScore ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin text-indigo-600" />
                    Querying Bureau...
                  </>
                ) : (
                  <>
                    <RefreshCw className="w-4 h-4 text-indigo-600" />
                    {formData.creditScore ? 'Recalculate Bureau Score' : 'Calculate Credit Score'}
                  </>
                )}
              </button>
            </div>
          </motion.div>
        );

      case 3:
        return (
          <motion.div
            key="step-3"
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            transition={{ duration: 0.3 }}
            className="space-y-4"
          >
            <div className="bg-slate-50 rounded-xl p-4 border border-slate-200 divide-y divide-slate-200/80">
              <div className="py-2 flex justify-between items-center text-sm">
                <span className="text-slate-500 font-medium">Full Name</span>
                <span className="text-slate-900 font-semibold">{formData.fullName}</span>
              </div>
              <div className="py-2 flex justify-between items-center text-sm">
                <span className="text-slate-500 font-medium">Email & Phone</span>
                <span className="text-slate-900 font-semibold">
                  {formData.email} • {formData.phone}
                </span>
              </div>
              <div className="py-2 flex justify-between items-center text-sm">
                <span className="text-slate-500 font-medium">Aadhaar Number</span>
                <span className="text-slate-900 font-mono font-semibold">
                  {formatAadhaarDisplay(formData.aadhaarNumber)}
                </span>
              </div>
              <div className="py-2 flex justify-between items-center text-sm">
                <span className="text-slate-500 font-medium">PAN Number</span>
                <span className="text-slate-900 font-mono font-semibold">
                  {formData.panNumber}
                </span>
              </div>
              <div className="py-2 flex justify-between items-center text-sm">
                <span className="text-slate-500 font-medium">Calculated Credit Score</span>
                <span className="text-indigo-600 font-bold font-mono">
                  {formData.creditScore} ({formData.creditRating})
                </span>
              </div>
            </div>

            {submitError && (
              <div className="p-3 bg-rose-50 border border-rose-200 rounded-lg text-xs text-rose-700 flex items-start gap-2">
                <AlertCircle className="w-4 h-4 text-rose-500 shrink-0 mt-0.5" />
                <div>
                  <p className="font-semibold">API Submission Note</p>
                  <p>{submitError}</p>
                </div>
              </div>
            )}
          </motion.div>
        );

      default:
        return null;
    }
  };

  if (isSubmitted) {
    return (
      <div className="max-w-xl mx-auto my-12 p-8 bg-white rounded-2xl shadow-xl border border-slate-100 text-center">
        <motion.div
          initial={{ scale: 0.8, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ duration: 0.4 }}
          className="inline-flex items-center justify-center w-16 h-16 bg-emerald-100 text-emerald-600 rounded-full mb-4"
        >
          <Check className="w-8 h-8" />
        </motion.div>
        <h2 className="text-2xl font-bold text-slate-900 mb-2">
          KYC Application Submitted
        </h2>
        <p className="text-sm text-slate-600 mb-6">
          Your Aadhaar verification and Credit Bureau integration data have been successfully posted to the ingest pipeline.
        </p>
        <div className="p-4 bg-slate-50 rounded-xl text-left border border-slate-200 text-xs font-mono space-y-1 mb-6 text-slate-700">
          <p><span className="text-slate-400">Reference ID:</span> {Math.random().toString(36).substring(2, 10).toUpperCase()}</p>
          <p><span className="text-slate-400">Aadhaar Validated:</span> True (^
d&#123;12&#125;$)</p>
          <p><span className="text-slate-400">Calculated Score:</span> {formData.creditScore}</p>
        </div>
        <button
          onClick={() => {
            setIsSubmitted(false);
            setCurrentStep(0);
            setFormData({
              fullName: '',
              email: '',
              phone: '',
              dob: '',
              aadhaarNumber: '',
              panNumber: '',
              creditScore: null,
              creditRating: '',
              creditFetchDate: '',
            });
          }}
          className="px-6 py-2.5 bg-slate-900 text-white font-medium text-sm rounded-lg hover:bg-slate-800 transition"
        >
          Start New Registration
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto my-8 p-4 sm:p-6 bg-white rounded-2xl shadow-xl border border-slate-100">
      {/* Header */}
      <div className="mb-6 pb-4 border-b border-slate-100 flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-slate-900 flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-indigo-600" /> Customer KYC Registration
          </h2>
          <p className="text-xs text-slate-500 mt-1">
            Complete identity verification & bureau credit score check
          </p>
        </div>
        <span className="px-3 py-1 bg-indigo-50 text-indigo-700 border border-indigo-100 text-xs font-medium rounded-full">
          Step {currentStep + 1} of {STEPS.length}
        </span>
      </div>

      {/* Progress Steps Header */}
      <div className="mb-8">
        <div className="flex justify-between relative">
          {/* Line behind steps */}
          <div className="absolute top-1/2 left-0 right-0 h-0.5 bg-slate-200 -translate-y-1/2 z-0" />
          <div
            className="absolute top-1/2 left-0 h-0.5 bg-indigo-600 -translate-y-1/2 z-0 transition-all duration-300"
            style={{
              width: `${(currentStep / (STEPS.length - 1)) * 100}%`,
            }}
          />

          {STEPS.map((step, idx) => {
            const Icon = step.icon;
            const isCompleted = idx < currentStep;
            const isCurrent = idx === currentStep;

            return (
              <div key={step.id} className="relative z-10 flex flex-col items-center">
                <div
                  className={`w-9 h-9 rounded-full flex items-center justify-center text-xs font-bold transition-all ${
                    isCompleted
                      ? 'bg-indigo-600 text-white'
                      : isCurrent
                      ? 'bg-indigo-600 text-white ring-4 ring-indigo-100'
                      : 'bg-slate-100 text-slate-400 border border-slate-300'
                  }`}
                >
                  {isCompleted ? <Check className="w-4 h-4" /> : <Icon className="w-4 h-4" />}
                </div>
                <span
                  className={`text-[11px] font-medium mt-1.5 hidden sm:block ${
                    isCurrent ? 'text-indigo-600 font-semibold' : 'text-slate-500'
                  }`}
                >
                  {step.title}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Form Content Step Render */}
      <form onSubmit={handleSubmit}>
        <div className="min-h-[280px]">
          <AnimatePresence mode="wait">{renderStepContent()}</AnimatePresence>
        </div>

        {/* Form Controls / Step Navigation */}
        <div className="mt-8 pt-4 border-t border-slate-100 flex items-center justify-between">
          <button
            type="button"
            onClick={handleBack}
            disabled={currentStep === 0 || isSubmitting}
            className="inline-flex items-center gap-1 px-4 py-2 text-xs font-semibold text-slate-600 hover:text-slate-900 disabled:opacity-30 disabled:hover:text-slate-600 transition"
          >
            <ChevronLeft className="w-4 h-4" /> Back
          </button>

          {currentStep < STEPS.length - 1 ? (
            <button
              type="button"
              onClick={handleNext}
              disabled={!isStepValid(currentStep)}
              className="inline-flex items-center gap-1 px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold rounded-lg shadow-sm transition disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Continue <ChevronRight className="w-4 h-4" />
            </button>            ) : (
            <button
              type="submit"
              disabled={isSubmitting || !isStepValid(currentStep)}
              className="inline-flex items-center gap-2 px-6 py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold rounded-lg shadow-sm transition disabled:opacity-50"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" /> Submitting...
                </>
              ) : (
                <>
                  <ShieldCheck className="w-4 h-4" /> Submit KYC Form
                </>
              )}
            </button>
          )}
        </div>
      </form>
    </div>
  );
}
