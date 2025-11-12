import os
import time
import pandas as pd
from typing import Optional, Dict, List, Tuple

# Optional imports - only needed if Google Sheets is configured
try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False
    gspread = None
    Credentials = None

try:
    import streamlit as st
except ImportError:
    st = None


@st.cache_resource
def get_client():
    """Cached function to get Google Sheets client."""
    
    if not GSPREAD_AVAILABLE:
        st.warning("Google Sheets packages not installed. Please add `gspread` and `google-auth` to requirements.txt.")
        return None, None

    try:
        creds = None
        service_account_email = None
        
        if 'gcp_service_account' in st.secrets:
            info_dict = dict(st.secrets['gcp_service_account'])
            creds = Credentials.from_service_account_info(info_dict, scopes=SheetsManager.SCOPES)
            service_account_email = info_dict.get('client_email')
        elif 'GOOGLE_SERVICE_ACCOUNT_JSON' in st.secrets:
            import json
            json_str = st.secrets['GOOGLE_SERVICE_ACCOUNT_JSON']
            if json_str:
                info = json.loads(json_str)
                creds = Credentials.from_service_account_info(info, scopes=SheetsManager.SCOPES)
                service_account_email = info.get('client_email')
        
        if creds is None:
            st.error("Google Sheets credentials not found in Streamlit secrets.")
            return None, None
            
        client = gspread.authorize(creds)
        return client, service_account_email

    except Exception as e:
        st.error(f"A critical error occurred during Google Sheets client initialization: {str(e)}")
        return None, None


class SheetsManager:
    """Manages Google Sheets API operations."""
    
    # Define the scope for Google Sheets API
    SCOPES = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    
    def __init__(self, spreadsheet_id: Optional[str] = None):
        """
        Initialize Google Sheets manager.
        
        Args:
            spreadsheet_id: Google Sheets spreadsheet ID (from the URL)
        """
        # Try multiple sources for spreadsheet ID:
        # 1. Passed as parameter
        # 2. Environment variable
        # 3. Streamlit secrets (for Streamlit Cloud) - checked lazily
        if spreadsheet_id:
            self.spreadsheet_id = spreadsheet_id
        else:
            self.spreadsheet_id = os.getenv("GOOGLE_SHEETS_ID")

        self.client, self.service_account_email = get_client()
        self.spreadsheet = None
        
        if self.client and self.spreadsheet_id:
            try:
                self.spreadsheet = self.client.open_by_key(self.spreadsheet_id)
            except gspread.exceptions.SpreadsheetNotFound:
                st.error(f"Spreadsheet with ID '{self.spreadsheet_id}' not found or not shared with service account.")
                self.spreadsheet = None
            except Exception as e:
                st.error(f"Error opening spreadsheet: {e}")
                self.spreadsheet = None
    
    def _get_spreadsheet_id(self) -> Optional[str]:
        """Lazily get spreadsheet ID, trying Streamlit secrets if not already set."""
        if self.spreadsheet_id:
            return self.spreadsheet_id
        
        # Try Streamlit secrets (lazy access - only when needed)
        try:
            import streamlit as st
            if hasattr(st, 'secrets'):
                try:
                    # Try to get the secret value directly
                    # st.secrets can be accessed like a dict or attribute
                    secret_value = None
                    try:
                        # Try dict-like access first
                        secret_value = st.secrets.get('GOOGLE_SHEETS_ID') or st.secrets['GOOGLE_SHEETS_ID']
                    except (KeyError, AttributeError, TypeError):
                        # Try attribute access
                        try:
                            secret_value = getattr(st.secrets, 'GOOGLE_SHEETS_ID', None)
                        except (AttributeError, RuntimeError):
                            pass
                    
                    if secret_value:
                        self.spreadsheet_id = str(secret_value).strip()
                        return self.spreadsheet_id
                except (RuntimeError, AttributeError, KeyError, TypeError) as e:
                    # Not in Streamlit context or secrets not available
                    # Silently fail - this is expected if not in Streamlit context
                    pass
        except (NameError, ImportError):
            pass
        
        return self.spreadsheet_id

    def get_spreadsheet(self):
        """
        Return the gspread Spreadsheet object using the stored spreadsheet ID.
        Ensures the client and spreadsheet are initialized before returning.
        """
        # If spreadsheet already initialized, reuse it
        if hasattr(self, "spreadsheet") and self.spreadsheet is not None:
            return self.spreadsheet

        # Ensure client is initialized
        if not self.client:
            if hasattr(self, "_initialize_client"):
                self._initialize_client()
            else:
                raise RuntimeError("Google Sheets client not initialized.")

        # Ensure spreadsheet ID is known
        if not self.spreadsheet_id:
            self.spreadsheet_id = self._get_spreadsheet_id()

        if not self.spreadsheet_id:
            raise RuntimeError("Spreadsheet ID not found in secrets or config.")

        # Open the spreadsheet using gspread
        try:
            self.spreadsheet = self.client.open_by_key(self.spreadsheet_id)
            return self.spreadsheet
        except Exception as e:
            if st and hasattr(st, "error"):
                st.error(f"Failed to open spreadsheet: {e}")
            raise

    def is_configured(self) -> bool:
        """Check if Google Sheets is properly configured."""
        # Update spreadsheet_id from secrets if needed
        if not self.spreadsheet_id:
            self.spreadsheet_id = self._get_spreadsheet_id()
        
        # If we now have a spreadsheet_id but no client, try to initialize
        if self.spreadsheet_id and not self.client:
            self._initialize_client()
        
        return self.client is not None and self.spreadsheet is not None

    def get_service_account_email(self) -> Optional[str]:
        """Return detected service account email if available."""
        return getattr(self, 'service_account_email', None)

    def get_credentials_source(self) -> Optional[str]:
        """Return which source supplied credentials: 'secrets_table' | 'secrets_json' | 'file' | None"""
        return getattr(self, 'credentials_source', None)
    
    def get_credentials_source(self) -> Optional[str]:
        """Return which source supplied credentials: 'secrets_table' | 'secrets_json' | 'file' | None"""
        return getattr(self, 'credentials_source', None)

    def get_or_create_worksheet(self, sheet_name: str, headers: List[str]):
        """
        Get or create worksheet, cached to avoid hitting Google API rate limits.
        """
        if not hasattr(self, "_ws_cache"):
            self._ws_cache = {}

        # ✅ Local cache: only call API once per session per sheet
        if sheet_name in self._ws_cache:
            return self._ws_cache[sheet_name]

        try:
            spreadsheet = self.get_spreadsheet()
            try:
                worksheet = spreadsheet.worksheet(sheet_name)
            except gspread.exceptions.WorksheetNotFound:
                # Create worksheet if not found
                cols = max(10, len(headers) or 10)
                worksheet = spreadsheet.add_worksheet(
                    title=sheet_name, rows="1000", cols=str(cols)
                )
                if headers:
                    worksheet.append_row(headers, value_input_option="USER_ENTERED")

            # Cache the worksheet object for this session
            self._ws_cache[sheet_name] = worksheet
            return worksheet

        except Exception as e:
            try:
                if st and hasattr(st, "error"):
                    st.error(f"Error getting/creating worksheet '{sheet_name}': {str(e)}")
            except Exception:
                print(f"ERROR: Error getting/creating worksheet '{sheet_name}': {str(e)}")
            return None


    def _get_dataframe_cache(self) -> Dict[Tuple[str, Tuple[str, ...]], Tuple[pd.DataFrame, float]]:
        """Return (and lazily create) the in-memory dataframe cache."""
        if not hasattr(self, "_df_cache"):
            self._df_cache = {}
        return self._df_cache

    def read_dataframe(
        self,
        sheet_name: str,
        headers: List[str],
        *,
        force_refresh: bool = False,
        ttl_seconds: int = 300,
        ) -> pd.DataFrame:
        """
        Read data from Google Sheet into pandas DataFrame.
        
        Args:
            sheet_name: Name of the worksheet
            headers: Expected column headers
            
        Returns:
            DataFrame with the data
        """
        if not self.is_configured():
            return pd.DataFrame(columns=headers)
        cache_key = (sheet_name, tuple(headers or []))
        cache = self._get_dataframe_cache()
        now = time.time()

        if not force_refresh and cache_key in cache:
            cached_df, cached_at = cache[cache_key]
            if ttl_seconds <= 0 or (now - cached_at) < ttl_seconds:
                return cached_df.copy(deep=True)
            # Stale entry; remove it before refreshing
            del cache[cache_key]

        try:
            worksheet = self.get_or_create_worksheet(sheet_name, headers)
            if worksheet is None:
                return pd.DataFrame(columns=headers)

            values = worksheet.get_all_values()

            if not values or len(values) <= 1:
                # Only headers or empty
                df = pd.DataFrame(columns=headers)
            else:
                df = pd.DataFrame(values[1:], columns=headers)
                df = df.dropna(how="all")  # Clean empty rows

            # Cache the freshly fetched dataframe
            cache[cache_key] = (df.copy(deep=True), now)
            return df

        except Exception as e:
            if st and hasattr(st, "error"):
                st.error(f"Error reading from sheet '{sheet_name}': {str(e)}")
            else:
                print(f"Error reading from sheet '{sheet_name}': {str(e)}")
            return pd.DataFrame(columns=headers)
    
    def write_dataframe(self, sheet_name: str, df: pd.DataFrame, headers: List[str]):
        """
        Write DataFrame to Google Sheet.
        
        Args:
            sheet_name: Name of the worksheet
            df: DataFrame to write
            headers: Column headers
        """
        if not self.is_configured():
            st.error("Google Sheets not configured. Cannot write data.")
            return False
        
        try:
            worksheet = self.get_or_create_worksheet(sheet_name, headers)
            if worksheet is None:
                return False
            
            # Clear existing data (keep headers)
            worksheet.clear()
            worksheet.append_row(headers)
            
            # Convert DataFrame to list of lists
            if not df.empty:
                values = df[headers].values.tolist()
                if values:
                    worksheet.append_rows(values)
            
            return True
            
        except Exception as e:
            st.error(f"Error writing to sheet '{sheet_name}': {str(e)}")
            return False
    
    def append_row(self, sheet_name: str, row_data: List, headers: List[str]) -> bool:
        """
        Append a single row to Google Sheet.
        
        Args:
            sheet_name: Name of the worksheet
            row_data: List of values for the row
            headers: Column headers
        """
        if not self.is_configured():
            return False
        
        try:
            worksheet = self.get_or_create_worksheet(sheet_name, headers)
            if worksheet is None:
                return False
            
            # Ensure row_data matches headers length
            while len(row_data) < len(headers):
                row_data.append("")
            
            worksheet.append_row(row_data[:len(headers)])
            return True
            
        except Exception as e:
            st.error(f"Error appending row to sheet '{sheet_name}': {str(e)}")
            return False
    
    def update_row(self, sheet_name: str, row_index: int, row_data: List, headers: List[str]) -> bool:
        """
        Update a specific row in Google Sheet (1-indexed, including header).
        
        Args:
            sheet_name: Name of the worksheet
            row_index: Row number (1-indexed, row 1 is headers)
            row_data: List of values for the row
            headers: Column headers
        """
        if not self.is_configured():
            return False
        
        try:
            worksheet = self.get_or_create_worksheet(sheet_name, headers)
            if worksheet is None:
                return False
            
            # Ensure row_data matches headers length
            while len(row_data) < len(headers):
                row_data.append("")
            
            # Update row (row_index is 1-indexed, so row 2 is first data row)
            worksheet.update(f"A{row_index}", [row_data[:len(headers)]], value_input_option='RAW')
            return True
            
        except Exception as e:
            st.error(f"Error updating row in sheet '{sheet_name}': {str(e)}")
            return False
    
    def delete_rows(self, sheet_name: str, row_indices: List[int]) -> bool:
        """
        Delete rows from Google Sheet (1-indexed, including header).
        
        Args:
            sheet_name: Name of the worksheet
            row_indices: List of row numbers to delete (1-indexed)
        """
        if not self.is_configured():
            return False
        
        try:
            worksheet = self.get_or_create_worksheet(sheet_name, [])
            if worksheet is None:
                return False
            
            # Sort indices descending to avoid index shifting issues
            sorted_indices = sorted(row_indices, reverse=True)
            
            for row_idx in sorted_indices:
                worksheet.delete_rows(row_idx)
            
            return True
            
        except Exception as e:
            st.error(f"Error deleting rows from sheet '{sheet_name}': {str(e)}")
            return False
    
    def create_spreadsheet(self, title: str) -> Optional[str]:
        """
        Create a new Google Spreadsheet.
        
        Args:
            title: Title of the spreadsheet
            
        Returns:
            Spreadsheet ID if successful, None otherwise
        """
        if not self.client:
            st.error("Google Sheets client not initialized. Cannot create spreadsheet.")
            return None
        
        try:
            spreadsheet = self.client.create(title)
            # Share with service account email if needed (optional)
            return spreadsheet.id
        except Exception as e:
            st.error(f"Error creating spreadsheet: {str(e)}")
 
            return None



