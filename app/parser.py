import re
from datetime import datetime
import html
from bs4 import BeautifulSoup

def parse_email(body: str) -> dict:
    """
    Master parser dispatcher.
    Detects email type and routes to specific parser.
    """

    body_lower = body.lower()


    # 1️⃣ Ignore login / security notifications (extended)
    if (
        "usuario de bdp se ha usado recientemente" in body_lower
        or "intento fallido por biometría" in body_lower
        or "intento fallido por biometria" in body_lower
        or "ha registrado el equipo" in body_lower
        or "banca virtual intermatico" in body_lower and "dispositivo con la siguiente ip" in body_lower
    ):
        return {"type": "ignore_only_info"}
    
    # 2️⃣ Beneficiary / account registration confirmation
    if (
        "registro de la cuenta" in body_lower
        and "se realizó exitosamente" in body_lower
    ):
        return {"type": "ignore_only_info"}

    # 2️⃣ Credit card statement
    if "estado de cuenta" in body_lower and "saldo al corte" in body_lower:
        return parse_statement_email(body)
    # 3️⃣ Incoming transfer (money received)
    if (
        "enviar dinero a tu cuenta" in body_lower
        or "valor que recibiste" in body_lower
    ):
        return parse_incoming_transfer(body)

    # 3️⃣ Transfer emails
    if "envío de dinero" in body_lower or "envio de dinero" in body_lower:
        return parse_transfer_email(body)

    # 4️⃣ Account purchase (debito mensual format)
    if (
        "se ha realizado el débito mensual" in body_lower
        and "establecimiento" in body_lower
        and "monto" in body_lower
    ):
        return parse_account_purchase(body)

    # 5️⃣ Credit card purchase (old format)
    if "ha realizado una transacción con su tarjeta pacificard" in body_lower:
        return parse_credit_card_transaction(body)
    
    # 5️⃣ Credit card renewal charges
    if (
        "servicio anual de prestaciones del exterior" in body_lower
        or "plan de recompensas" in body_lower
    ) and "monto:" in body_lower:
        return parse_credit_card_transaction(body)

    # 5️⃣ Utility payment
    if "servicio:" in body_lower and "valor:" in body_lower:
        return parse_service_payment(body)

    # 6️⃣ Credit card payment (all variants)
    if (
        "precancelar diferido" in body_lower
        or "agradece su pago de" in body_lower
        or "pago a tu tarjeta de crédito" in body_lower
        or (
            re.search(r"tarjeta\s*:", body_lower)
            and re.search(r"valor\s*:", body_lower)
        )
    ):
        return parse_card_payment(body)

    return {"type": "ignore"}


# -------------------------------------------------------
# CREDIT CARD PURCHASE
# -------------------------------------------------------

def parse_credit_card_transaction(body: str):

    # --- Merchant ---
    merchant_match = re.search(
        r"Establecimiento:\s*(.+?)(?:Fecha|Monto|$)",
        body,
        re.IGNORECASE | re.DOTALL
    )

    if merchant_match:
        merchant = merchant_match.group(1).strip()
    else:
        if "prestaciones del exterior" in body.lower():
            merchant = "Pacificard Annual International Service"
        elif "plan de recompensas" in body.lower():
            merchant = "Pacificard Rewards Program"
        else:
            merchant = "Pacificard Charge"

    # -------------------------------------------------
    # --- Amount (supports multiple formats) ---
    # -------------------------------------------------

    amount_match = re.search(
        r"Monto\s*:?\s*\$?\s*([\d]+(?:\.\d{1,2})?)",
        body,
        re.IGNORECASE
    )

    amount = float(amount_match.group(1)) if amount_match else None

    # -------------------------------------------------
    # --- Date (supports BOTH formats) ---
    # -------------------------------------------------

    date = None

    # Format 1:
    # Fecha del cargo: 02/02/2026
    date_slash_match = re.search(
        r"Fecha del cargo:\s*(\d{2}/\d{2}/\d{4})",
        body,
        re.IGNORECASE
    )

    # Format 2:
    # Fecha de la transacción 2026-02-15 a las 17:54
    date_dash_match = re.search(
        r"Fecha de la transacción\s*(\d{4}-\d{2}-\d{2})\s*a las\s*(\d{2}:\d{2})",
        body,
        re.IGNORECASE
    )

    try:
        if date_dash_match:
            date_str = f"{date_dash_match.group(1)} {date_dash_match.group(2)}"
            date = datetime.strptime(date_str, "%Y-%m-%d %H:%M")

        elif date_slash_match:
            date = datetime.strptime(date_slash_match.group(1), "%d/%m/%Y")

    except Exception as e:
        print("Credit card date parse error:", e)

    return {
        "type": "transaction",
        "transaction_type": "expense",
        "amount": amount,
        "merchant_raw": merchant,
        "date": date,
        "metadata": {
            "source": "credit_card"
        }
    }
# -------------------------------------------------------
# ACCOUNT PURCHASE (Debito mensual format)
# -------------------------------------------------------

def parse_account_purchase(body: str):

    # --- Merchant ---
    merchant_match = re.search(
        r"Establecimiento:\s*(.+?)(?:Fecha|Monto|$)",
        body,
        re.IGNORECASE | re.DOTALL
    )
    merchant = merchant_match.group(1).strip() if merchant_match else None

    # --- Amount ---
    amount_match = re.search(
        r"Monto.*?\$?\s*([\d]+(?:\.\d{1,2})?)",
        body,
        re.IGNORECASE
    )
    amount = float(amount_match.group(1)) if amount_match else None

    # --- Date ---
    date = None
    date_match = re.search(
        r"Fecha.*?(\d{4}-\d{2}-\d{2})",
        body,
        re.IGNORECASE
    )

    if date_match:
        try:
            date = datetime.strptime(date_match.group(1), "%Y-%m-%d")
        except Exception as e:
            print("Account purchase date parse error:", e)

    return {
        "type": "account_purchase",   # ← NEW DOCUMENT TYPE
        "transaction_type": "expense",
        "amount": amount,
        "merchant_raw": merchant,
        "date": date,
        "metadata": {
            "source": "account_purchase",
            "bank": "bdp"
        }
    }

# -------------------------------------------------------
# SERVICE PAYMENT (Electricity, etc.)
# -------------------------------------------------------

def parse_service_payment(body: str):

    service_match = re.search(r"Servicio:\s*(.+)", body)
    amount_match = re.search(r"Valor:\s*\$([\d\.]+)", body)
    date_match = re.search(r"Fecha y hora:\s*([\d\-]+)\s*a las\s*([\d:]+)", body)

    merchant = service_match.group(1).strip() if service_match else None
    amount = float(amount_match.group(1)) if amount_match else None

    date = None
    if date_match:
        try:
            date_str = f"{date_match.group(1)} {date_match.group(2)}"
            date = datetime.strptime(date_str, "%d-%m-%Y %H:%M")
        except:
            pass

    return {
        "type": "transaction",
        "transaction_type": "expense",
        "amount": amount,
        "merchant_raw": merchant,
        "date": date,
        "metadata": {"source": "service_payment"}
    }


# -------------------------------------------------------
# TRANSFER EMAIL
# -------------------------------------------------------

def parse_transfer_email(body: str):

    amount_match = re.search(
    r"Valor(?: que enviaste)?:\s*\$?\s*([\d\.]+)",
    body,
    re.IGNORECASE
    )
    destination_match = re.search(r"Banco de destino:\s*(.+)", body)
    motive_match = re.search(r"Motivo del envío:\s*(.+?)(?:Número de comprobante:|Fecha y hora:)", body, re.DOTALL)
    date_match = re.search(r"Fecha y hora:\s*(\d{2}-\d{2}-\d{4})\s*a las\s*(\d{2}:\d{2})", body)

    amount = float(amount_match.group(1)) if amount_match else None
    destination_bank = destination_match.group(1).strip() if destination_match else None
    motive = motive_match.group(1).strip() if motive_match else None

    # ---- Date Parsing ----
    date = None
    if date_match:
        try:
            date_str = f"{date_match.group(1)} {date_match.group(2)}"
            date = datetime.strptime(date_str, "%d-%m-%Y %H:%M")
        except Exception as e:
            print("Transfer date parse error:", e)

    # ---- Detect savings ----
    if destination_bank and "PRODUBANCO" in destination_bank.upper():
        transaction_type = "savings"
    else:
        transaction_type = "transfer"

    return {
        "type": "transaction",
        "transaction_type": transaction_type,
        "amount": amount,
        "merchant_raw": motive,
        "date": date,
        "metadata": {
            "source": "transfer",
            "destination_bank": destination_bank
        }
    }


# -------------------------------------------------------
# CREDIT CARD PAYMENT
# -------------------------------------------------------

def parse_card_payment(body: str):

    # --- Amount ---
    amount_match = (
        re.search(r"pago de\s*([\d\.]+)", body, re.IGNORECASE)
        or re.search(r"Valor:\s*\$?:?\s*([\d\.]+)", body, re.IGNORECASE)
    )

    amount = float(amount_match.group(1)) if amount_match else None

    # --- Date ---
    date = None

    # Format 1: 27/02/2026
    date_match_slash = re.search(r"(\d{2}/\d{2}/\d{4})", body)

    # Format 2: 27-02-2026 a las 11:58
    date_match_dash = re.search(
        r"Fecha y hora:\s*(\d{2}-\d{2}-\d{4})\s*a las\s*(\d{2}:\d{2})",
        body
    )

    try:
        if date_match_dash:
            date_str = f"{date_match_dash.group(1)} {date_match_dash.group(2)}"
            date = datetime.strptime(date_str, "%d-%m-%Y %H:%M")

        elif date_match_slash:
            date = datetime.strptime(date_match_slash.group(1), "%d/%m/%Y")

    except Exception as e:
        print("Card payment date parse error:", e)

    return {
        "type": "transaction",
        "transaction_type": "payment",
        "amount": amount,
        "merchant_raw": "Pacificard Payment",
        "date": date,
        "metadata": {"source": "card_payment"}
    }


# -------------------------------------------------------
# STATEMENT EMAIL
# -------------------------------------------------------

def parse_statement_email(body: str):

    saldo_match = re.search(r"Saldo al corte\s*\$?\s*([\d,\.]+)", body)
    pago_minimo_match = re.search(r"Pago mínimo\s*\$?\s*([\d,\.]+)", body)
    pago_sugerido_match = re.search(r"Pago sugerido\s*\$?\s*([\d,\.]+)", body)
    fecha_corte_match = re.search(r"(\d{2}/[A-Z]{3}/\d{4})", body)

    return {
        "type": "statement",
        "transaction_type": None,
        "amount": None,
        "merchant_raw": None,
        "date": None,
        "metadata": {
            "saldo_corte": float(saldo_match.group(1).replace(",", "")) if saldo_match else None,
            "pago_minimo": float(pago_minimo_match.group(1).replace(",", "")) if pago_minimo_match else None,
            "pago_sugerido": float(pago_sugerido_match.group(1).replace(",", "")) if pago_sugerido_match else None,
            "fecha_corte": fecha_corte_match.group(1) if fecha_corte_match else None,
            "source": "statement"
        }
    }

# -------------------------------------------------------
# INCOMING TRANSFER (Income to account)
# -------------------------------------------------------

def parse_incoming_transfer(body: str):

    # --- Amount ---
    amount_match = re.search(
        r"Valor que recibiste:\s*\$?\s*([\d]+(?:\.\d{1,2})?)",
        body,
        re.IGNORECASE
    )

    amount = float(amount_match.group(1)) if amount_match else None

    # --- Motive ---
    motive_match = re.search(
        r"Motivo del envío:\s*(.+?)(?:Fecha y hora:|Cargo:|$)",
        body,
        re.IGNORECASE | re.DOTALL
    )

    motive = motive_match.group(1).strip() if motive_match else None

    # --- Date ---
    date = None
    date_match = re.search(
        r"Fecha y hora:\s*(\d{2}-\d{2}-\d{4})\s*a las\s*(\d{2}:\d{2})",
        body
    )

    if date_match:
        try:
            date_str = f"{date_match.group(1)} {date_match.group(2)}"
            date = datetime.strptime(date_str, "%d-%m-%Y %H:%M")
        except Exception as e:
            print("Incoming transfer date parse error:", e)

    return {
        "type": "transaction",
        "transaction_type": "income",
        "amount": amount,
        "merchant_raw": motive,
        "date": date,
        "metadata": {
            "source": "incoming_transfer",
            "direction": "inbound"
        }
    }

def clean_email_body(decoded_body: str) -> str:

    #Always stript HTML tags
    soup = BeautifulSoup(decoded_body, "html.parser")
    decoded_body = soup.get_text(separator=" ")

    # Decode HTML entities
    decoded_body = html.unescape(decoded_body)

    # Replace non-breaking spaces
    decoded_body = decoded_body.replace("\xa0", " ")
    decoded_body = decoded_body.replace("&nbsp", " ")

    # Collapse multiple whitespace
    decoded_body = re.sub(r"\s+", " ", decoded_body)

    return decoded_body.strip()