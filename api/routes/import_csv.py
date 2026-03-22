"""CSV import for bank transactions"""

from fastapi import APIRouter, File, UploadFile, HTTPException
import csv
import io
from datetime import datetime

from services.bank_integration import BankIntegrationService

router = APIRouter(prefix="/api/v1/import", tags=["import"])


@router.post("/csv")
async def import_csv(file: UploadFile = File(...)):
    """Import CSV file with bank transactions"""
    
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be CSV format")
    
    try:
        contents = await file.read()
        text = contents.decode('utf-8')
        
        # Parse CSV
        reader = csv.DictReader(io.StringIO(text))
        transactions = []
        
        for row in reader:
            # Expect columns: date, description, amount, counterparty
            transaction = {
                'date': row.get('date') or row.get('Datum') or row.get('Date'),
                'description': row.get('description') or row.get('Beskrivning') or row.get('Description'),
                'amount': float(row.get('amount') or row.get('Belopp') or 0),
                'counterparty': row.get('counterparty') or row.get('Motpart') or row.get('Counterparty') or 'Unknown',
            }
            transactions.append(transaction)
        
        # Import using bank service
        service = BankIntegrationService()
        imported_count = 0
        duplicates = 0
        
        for txn in transactions:
            try:
                service.import_transaction(
                    date=datetime.fromisoformat(txn['date']),
                    description=txn['description'],
                    amount=txn['amount'],
                    counterparty=txn['counterparty'],
                )
                imported_count += 1
            except Exception as e:
                # Likely a duplicate
                duplicates += 1
        
        return {
            "status": "success",
            "imported": imported_count,
            "duplicates": duplicates,
            "total": len(transactions),
            "message": f"Imported {imported_count} transactions, {duplicates} duplicates skipped",
        }
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error parsing CSV: {str(e)}")
