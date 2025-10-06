# Stock Management System

## Overview

This is a Streamlit-based stock management application designed to track inventory across multiple categories (Paper, Inks, Chemicals, Poly Films). The system provides transaction tracking, current stock monitoring, template management for recurring entries, and reporting capabilities. It features password-based authentication with SHA256 hashing and CSV-based data persistence.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Application Framework
**Decision:** Streamlit for the entire application stack
- **Rationale:** Streamlit provides rapid development of data-centric web applications with minimal code
- **Pros:** Fast prototyping, built-in UI components, easy deployment, Python-native
- **Cons:** Limited customization compared to traditional web frameworks, session state management can be tricky

### Authentication System
**Decision:** File-based authentication with SHA256 password hashing
- **Problem:** Need simple user authentication without database overhead
- **Solution:** Single-user system storing hashed password in `data/password.txt`
- **Components:**
  - `AuthManager` class handles login, logout, and password changes
  - Default credentials: password "admin123" (hash stored in file)
  - Session state tracks authentication status
- **Pros:** Simple to implement, no database required, secure password storage
- **Cons:** Single-user only, not scalable for multi-user scenarios

### Data Storage Architecture
**Decision:** CSV-based file storage instead of database
- **Problem:** Need persistent data storage for inventory tracking
- **Solution:** Three separate CSV files managed by `DataManager` class:
  1. `transactions.csv` - All inventory movements (in/out)
  2. `current_stock.csv` - Current inventory levels by category/subcategory
  3. `templates.csv` - Saved transaction templates for quick entry
- **Pros:** No database setup required, human-readable, easy backup, portable
- **Cons:** Not suitable for high-volume concurrent access, slower for large datasets, no ACID guarantees

### Data Schema Design

**Transactions Table:**
- `id`: Unique transaction identifier
- `category`: Main category (Paper, Inks, Chemicals, Poly Films)
- `subcategory`: Specific item type
- `transaction_type`: "IN" or "OUT"
- `quantity`: Amount of stock movement
- `date`: Transaction date
- `supplier`: Supplier/source name
- `notes`: Additional information
- `created_at`: Record creation timestamp

**Stock Table:**
- `category`: Main category
- `subcategory`: Specific item type
- `remaining_qty`: Current quantity in stock
- `last_updated`: Last modification timestamp
- `supplier`: Primary supplier

**Templates Table:**
- `id`: Unique template identifier
- `template_name`: User-defined template name
- `category`: Category for quick entry
- `subcategory`: Subcategory for quick entry
- `supplier`: Default supplier
- `created_at`: Template creation timestamp

### Application Structure
**Decision:** Modular component-based architecture
- **Core Modules:**
  - `app.py`: Main application entry point with Streamlit UI
  - `auth.py`: Authentication logic
  - `data_manager.py`: Data persistence and business logic
  - `utils.py`: Shared utility functions (date formatting, validation, Excel parsing)
- **Rationale:** Separation of concerns for maintainability and testability
- **Pros:** Clear boundaries, easier testing, reusable components
- **Cons:** More files to manage

### State Management
**Decision:** Streamlit session state for runtime data
- **Solution:** Store `DataManager`, `AuthManager`, and authentication status in session state
- **Rationale:** Persist data across user interactions within a session
- **Limitation:** State resets on app restart/refresh

### User Interface Pattern
**Decision:** Tab-based navigation with sidebar settings
- **Layout:** 
  - Sidebar: Logout, global search, settings, password change
  - Main area: 6 tabs (Dashboard, Paper, Inks, Chemicals, Poly Films, Reports)
- **Rationale:** Intuitive category-based navigation for different inventory types
- **Pros:** Clean separation of functionality, familiar UI pattern

## Key Features

### Authentication & Security
- Password-protected access with SHA256 hashing
- Login/logout functionality
- Password change capability
- Default password: "admin123" (should be changed on first login)

### Inventory Management
- Four main categories: Paper (with supplier tracking), Inks, Chemicals, Poly Films
- Customizable subcategories for different sizes and variations
- Stock In/Out transaction recording with dates and quantities
- Real-time stock level calculations
- Transaction history tracking

### Search & Filtering
- Global search bar in sidebar (searches across all transactions)
- Advanced filtering in Reports tab (by date range, category, transaction type, subcategory)
- Text search across notes, supplier names, and product names

### Templates for Quick Entry
- Save frequently-used products as templates
- Quick load templates for faster data entry
- Auto-fill subcategory and supplier information
- Works for both existing and new products

### Data Import/Export
- Excel file upload for bulk transaction imports
- CSV and Excel export from Reports tab
- Expected format guides for uploads

### Analytics & Reporting
- Dashboard with stock overview and low stock alerts
- Visual charts showing stock movement trends over time
- Transaction reports with date filtering
- Stock In vs Stock Out comparisons by category

## External Dependencies

### Core Frameworks
- **Streamlit**: Web application framework and UI components
- **Pandas**: Data manipulation, CSV file handling, Excel import/export capabilities
- **Python Standard Library**: 
  - `datetime`: Date/time handling
  - `os`: File system operations
  - `hashlib`: Password hashing (SHA256)
  - `io.BytesIO`: In-memory file operations for Excel exports

### Data Persistence
- **File System**: All data stored in `data/` directory as CSV files
- **No Database**: System uses flat files instead of traditional RDBMS

### Future Integration Possibilities
The architecture suggests potential for:
- Excel import/export functionality (BytesIO import indicates planned Excel support)
- Reporting and analytics (dedicated Reports tab)
- Multi-category inventory management with subcategory hierarchies