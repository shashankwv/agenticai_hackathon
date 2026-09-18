import re
import logging
import importlib
import streamlit as st

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants (aligned to ETL / MDM contracts)
# ---------------------------------------------------------------------------
AADHAAR_PATTERN = re.compile(r'^\d{12}$')
AADHAAR_ERROR_MSG = 'Aadhaar Number must be exactly 12 digits'
CREDIT_SCORE_MIN = 300
CREDIT_SCORE_MAX = 900
CUSTOMER_TYPES = ['Individual', 'Sole Proprietor', 'HUF', 'Partnership', 'Company']


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _mask_aadhaar(value):
    """Return a PII-safe masked representation (only last 4 digits visible)."""
    if not value:
        return ''
    digits = str(value)
    if len(digits) <= 4:
        return 'X' * len(digits)
    return 'X' * (len(digits) - 4) + digits[-4:]


def validate_aadhaar(value):
    """Strict validation: exactly 12 numeric digits, no spaces or other characters."""
    if value is None:
        return False
    return bool(AADHAAR_PATTERN.match(str(value)))


def _coerce_credit_score(score):
    """Return an int in the 300-900 range or None if null/invalid/out-of-range."""
    if score is None or score == '':
        return None
    try:
        score_int = int(score)
    except (TypeError, ValueError):
        return None
    if score_int < CREDIT_SCORE_MIN or score_int > CREDIT_SCORE_MAX:
        return None
    return score_int


def _format_credit_score(score, has_response):
    """Human-readable read-only display value with graceful null/pending handling."""
    if score is None or score == '':
        return 'N/A' if has_response else 'Pending'
    coerced = _coerce_credit_score(score)
    return str(coerced) if coerced is not None else 'N/A'


def _init_state():
    defaults = {
        'credit_score': None,
        'kyc_has_response': False,
        'kyc_last_result': None,
        'aadhaar_touched': False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _on_aadhaar_change():
    """on-change callback; never logs the full Aadhaar value (PII)."""
    st.session_state['aadhaar_touched'] = True
    logger.debug('Aadhaar input changed (masked): %s',
                 _mask_aadhaar(st.session_state.get('aadhaar_input', '')))


def _extract_credit_score(response):
    if not isinstance(response, dict):
        return None
    if 'credit_score' in response:
        return response.get('credit_score')
    for container_key in ('data', 'payload', 'result', 'record'):
        container = response.get(container_key)
        if isinstance(container, dict) and 'credit_score' in container:
            return container.get('credit_score')
    return None


def _invoke_etl(form_data):
    """Dynamically import etl_pipeline and invoke process_and_store_kyc."""
    etl_module = importlib.import_module('etl_pipeline')
    process_fn = getattr(etl_module, 'process_and_store_kyc')
    return process_fn(form_data)


def _store_result(kind, message):
    st.session_state['kyc_last_result'] = {'kind': kind, 'message': message}


def _handle_response(response):
    """Translate ETL response dict into a UI result stored in session state."""
    if not isinstance(response, dict):
        _store_result('error', 'The KYC service returned an unexpected response format. Please try again or contact support.')
        return

    status = str(response.get('status', '')).strip().lower()
    detail = response.get('message') or response.get('detail') or ''

    score = _coerce_credit_score(_extract_credit_score(response))
    st.session_state['credit_score'] = score
    st.session_state['kyc_has_response'] = True

    if status == 'success':
        score_text = str(score) if score is not None else 'Pending'
        msg = 'KYC record processed and stored successfully. Calculated Credit Score: ' + score_text + '.'
        if detail:
            msg += ' ' + str(detail)
        _store_result('success', msg)
    elif status == 'requires_human_review':
        msg = ('KYC submission received, but schema resolution is pending Human-In-The-Loop validation. '
               'The record will be finalised once a reviewer approves the schema mapping.')
        if detail:
            msg += ' Details: ' + str(detail)
        _store_result('warning', msg)
    elif status == 'error':
        msg = 'The KYC request could not be processed.'
        if detail:
            msg += ' Reason: ' + str(detail)
        else:
            msg += ' Please verify the details and try again.'
        _store_result('error', msg)
    else:
        _store_result('error', 'The KYC service returned an unrecognised status. Please contact support if the issue persists.')


def _render_last_result():
    result = st.session_state.get('kyc_last_result')
    if not result:
        return
    kind = result.get('kind')
    message = result.get('message', '')
    if kind == 'success':
        st.success(message)
    elif kind == 'warning':
        st.warning(message)
    else:
        st.error(message)
    st.session_state['kyc_last_result'] = None


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------
def render_generated_ui():
    _init_state()

    st.title('Customer 360 - KYC Registration')
    st.caption('Core Banking | Jira CBC3-118 | Aadhaar capture and bureau credit score display')

    # ------------------------- Customer Details --------------------------
    st.subheader('Customer Details')
    col1, col2 = st.columns(2)
    with col1:
        full_name = st.text_input('Full Name', key='full_name_input',
                                  help='Customer legal name exactly as on the identity proof')
        dob = st.date_input('Date of Birth', key='dob_input')
        mobile_no = st.text_input('Mobile Number', key='mobile_input', max_chars=10,
                                  placeholder='10-digit mobile number')
    with col2:
        email = st.text_input('Email Address', key='email_input')
        pan_no = st.text_input('PAN', key='pan_input', max_chars=10, placeholder='ABCDE1234F')
        customer_type = st.selectbox('Customer Type', CUSTOMER_TYPES, key='customer_type_input')

    # --------------------- Regulatory Identifiers ------------------------
    st.subheader('Regulatory Identifiers')
    aadhaar_raw = st.text_input(
        'Aadhaar Number',
        key='aadhaar_input',
        max_chars=12,
        placeholder='Enter 12-digit Aadhaar number',
        help='Mandatory. Exactly 12 numeric digits; spaces and other characters are not allowed. Treated as sensitive PII.',
        on_change=_on_aadhaar_change,
    )
    aadhaar_raw = aadhaar_raw or ''
    aadhaar_valid = validate_aadhaar(aadhaar_raw)

    # Inline real-time validation message (accessibility-friendly text)
    if aadhaar_raw and not aadhaar_valid:
        st.error(AADHAAR_ERROR_MSG)
    elif aadhaar_valid:
        st.caption('Aadhaar Number format is valid (' + _mask_aadhaar(aadhaar_raw) + ').')
    elif st.session_state.get('aadhaar_touched'):
        st.error(AADHAAR_ERROR_MSG)

    # ------------------------ Credit Assessment --------------------------
    st.subheader('Credit Assessment')
    credit_display = _format_credit_score(st.session_state.get('credit_score'),
                                          st.session_state.get('kyc_has_response', False))
    st.text_input(
        'Calculated Credit Score',
        value=credit_display,
        disabled=True,
        help='Read-only. Populated from the credit bureau response via the ETL service (valid range 300-900).',
    )
    _render_last_result()

    # ------------------------- Payload assembly --------------------------
    form_data = {
        'full_name': (full_name or '').strip(),
        'date_of_birth': dob.isoformat() if dob else None,
        'mobile_no': (mobile_no or '').strip(),
        'email': (email or '').strip(),
        'pan_no': (pan_no or '').strip().upper(),
        'customer_type': customer_type,
        'aadhaar_no': aadhaar_raw if aadhaar_valid else None,
        'credit_score': _coerce_credit_score(st.session_state.get('credit_score')),
    }

    # --------------------------- Submission ------------------------------
    submit_disabled = not aadhaar_valid
    if submit_disabled:
        st.info('Submit is disabled until a valid 12-digit Aadhaar Number is entered.')

    submitted = st.button('Submit & Process KYC', type='primary',
                          disabled=submit_disabled, use_container_width=True)

    if submitted:
        # Defensive re-validation before dispatch
        if not validate_aadhaar(form_data.get('aadhaar_no')):
            st.error(AADHAAR_ERROR_MSG)
            return

        logger.info('Submitting KYC for customer (aadhaar masked): %s',
                    _mask_aadhaar(form_data.get('aadhaar_no')))

        with st.spinner('Processing KYC and retrieving credit bureau score...'):
            try:
                response = _invoke_etl(form_data)
                _handle_response(response)
            except ModuleNotFoundError:
                logger.exception('etl_pipeline module not found')
                _store_result('error', 'The ETL pipeline (etl_pipeline.py) is not available in this environment. Please contact the platform team.')
            except AttributeError:
                logger.exception('process_and_store_kyc missing from etl_pipeline')
                _store_result('error', 'The ETL pipeline does not expose process_and_store_kyc. Please contact the platform team.')
            except Exception:
                logger.exception('Unhandled error during KYC processing (aadhaar masked): %s',
                                 _mask_aadhaar(form_data.get('aadhaar_no')))
                _store_result('error', 'An unexpected error occurred while processing the KYC request. Please try again or contact support.')

        # Rerun so the read-only credit score and result banner reflect the response
        st.rerun()


if __name__ == '__main__':
    render_generated_ui()
