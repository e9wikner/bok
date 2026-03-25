"""API routes for anomaly detection."""

from fastapi import APIRouter, HTTPException, Query, status
from typing import Optional

from services.anomaly_detection import (
    AnomalyDetectionService,
    AnomalyThresholds,
)

router = APIRouter(prefix="/api/v1/anomalies", tags=["anomalies"])


@router.get("", response_model=dict)
async def detect_anomalies(
    period_id: Optional[str] = Query(None, description="Filtrera på period-ID"),
    rule_types: Optional[str] = Query(
        None,
        description="Kommaseparerade anomality-typer att köra (t.ex. 'unusual_amount,duplicate_entry')",
    ),
    min_score: float = Query(0.0, ge=0, le=1, description="Minsta anomali-score att inkludera"),
    limit: int = Query(50, ge=1, le=500, description="Max antal resultat"),
):
    """
    Kör anomalidetektering på bokföringsdata.
    
    Returnerar en lista med flaggade avvikelser sorterade efter score.
    
    **Anomalityper:**
    - `unusual_amount` – Ovanligt belopp på konto
    - `wrong_vat_code` – Felaktig momskod
    - `missing_counter_entry` – Saknar motkonto
    - `duplicate_entry` – Möjlig dubblettbokning
    - `frequent_small_transactions` – Många små transaktioner
    - `unusual_balance_change` – Ovanlig saldoförändring
    - `abnormal_voucher_count` – Onormalt antal verifikationer
    - `missing_attachment` – Saknar bilaga (BFL-krav)
    - `weekend_transaction` – Transaktion på helg
    """
    try:
        service = AnomalyDetectionService()
        
        types_list = None
        if rule_types:
            types_list = [t.strip() for t in rule_types.split(",")]
        
        anomalies = service.analyze(period_id=period_id, rule_types=types_list)
        
        # Filter by min score
        if min_score > 0:
            anomalies = [a for a in anomalies if a.score >= min_score]
        
        # Limit
        anomalies = anomalies[:limit]
        
        return {
            "total": len(anomalies),
            "period_id": period_id,
            "anomalies": [a.to_dict() for a in anomalies],
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Anomalidetektering misslyckades: {str(e)}",
        )


@router.get("/summary", response_model=dict)
async def anomaly_summary(
    period_id: Optional[str] = Query(None, description="Filtrera på period-ID"),
):
    """
    Sammanfattning av anomalier – perfekt för dashboard-widget.
    
    Returnerar antal per allvarlighetsgrad och typ, samt de 5 
    viktigaste avvikelserna.
    """
    try:
        service = AnomalyDetectionService()
        return service.get_summary(period_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Kunde inte generera anomali-sammanfattning: {str(e)}",
        )


@router.get("/voucher/{voucher_id}", response_model=dict)
async def check_voucher_anomalies(voucher_id: str):
    """
    Kontrollera en enskild verifikation för anomalier.
    
    Användbart att köra innan bokföring för att fånga fel tidigt.
    """
    try:
        service = AnomalyDetectionService()
        anomalies = service.analyze_voucher(voucher_id)
        
        return {
            "voucher_id": voucher_id,
            "total": len(anomalies),
            "has_critical": any(a.severity.value == "critical" for a in anomalies),
            "has_warning": any(a.severity.value == "warning" for a in anomalies),
            "anomalies": [a.to_dict() for a in anomalies],
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/types", response_model=dict)
async def list_anomaly_types():
    """
    Lista alla tillgängliga anomalityper med beskrivning.
    """
    types = {
        "unusual_amount": {
            "name": "Ovanligt belopp",
            "description": "Flaggar transaktioner med belopp som avviker statistiskt från kontots normala nivå.",
        },
        "wrong_vat_code": {
            "name": "Felaktig momskod",
            "description": "Identifierar konton med oväntade eller saknade momskoder.",
        },
        "missing_counter_entry": {
            "name": "Saknar motkonto",
            "description": "Verifikationer som bara har debet- eller kreditposter.",
        },
        "duplicate_entry": {
            "name": "Dubblettbokning",
            "description": "Verifikationer med samma belopp, datum och konton.",
        },
        "frequent_small_transactions": {
            "name": "Många små transaktioner",
            "description": "Ovanligt många transaktioner under tröskelvärdet mellan samma konton.",
        },
        "unusual_balance_change": {
            "name": "Ovanlig saldoförändring",
            "description": "Konton vars saldo ändrats dramatiskt mellan perioder.",
        },
        "abnormal_voucher_count": {
            "name": "Onormalt antal verifikationer",
            "description": "Perioder med ovanligt få eller många verifikationer.",
        },
        "missing_attachment": {
            "name": "Saknar bilaga",
            "description": "Verifikationer utan underlag – krävs enligt BFL.",
        },
        "weekend_transaction": {
            "name": "Helgtransaktion",
            "description": "Transaktioner daterade på lördag/söndag (möjligt datumfel).",
        },
    }
    return {"types": types}


@router.put("/thresholds", response_model=dict)
async def update_thresholds(
    unusual_amount_z_score: Optional[float] = Query(None, description="Z-score för ovanliga belopp"),
    min_transactions_for_stats: Optional[int] = Query(None, description="Minsta antal transaktioner för statistik"),
    frequent_small_tx_count: Optional[int] = Query(None, description="Gräns för 'många små transaktioner'"),
    small_tx_threshold: Optional[int] = Query(None, description="Belopp i öre under vilket transaktioner räknas som 'små'"),
    balance_change_pct: Optional[float] = Query(None, description="Procentuell saldoförändring för varning"),
    duplicate_window_days: Optional[int] = Query(None, description="Antal dagar för dubblettfönster"),
    voucher_count_z_score: Optional[float] = Query(None, description="Z-score för verifikationsantal"),
):
    """
    Uppdatera tröskelvärden för anomalidetektering.
    
    Returnerar de nya tröskelvärdena. I produktion bör dessa sparas per företag.
    """
    # In production, persist to database per company
    thresholds = AnomalyThresholds()
    
    if unusual_amount_z_score is not None:
        thresholds.unusual_amount_z_score = unusual_amount_z_score
    if min_transactions_for_stats is not None:
        thresholds.min_transactions_for_stats = min_transactions_for_stats
    if frequent_small_tx_count is not None:
        thresholds.frequent_small_tx_count = frequent_small_tx_count
    if small_tx_threshold is not None:
        thresholds.small_tx_threshold = small_tx_threshold
    if balance_change_pct is not None:
        thresholds.balance_change_pct = balance_change_pct
    if duplicate_window_days is not None:
        thresholds.duplicate_window_days = duplicate_window_days
    if voucher_count_z_score is not None:
        thresholds.voucher_count_z_score = voucher_count_z_score
    
    return {
        "message": "Tröskelvärden uppdaterade",
        "thresholds": {
            "unusual_amount_z_score": thresholds.unusual_amount_z_score,
            "min_transactions_for_stats": thresholds.min_transactions_for_stats,
            "frequent_small_tx_count": thresholds.frequent_small_tx_count,
            "small_tx_threshold": thresholds.small_tx_threshold,
            "balance_change_pct": thresholds.balance_change_pct,
            "duplicate_window_days": thresholds.duplicate_window_days,
            "voucher_count_z_score": thresholds.voucher_count_z_score,
        },
    }
