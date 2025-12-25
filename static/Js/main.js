// Common functions for all pages
document.addEventListener('DOMContentLoaded', function() {
    // Auto-close alerts after 5s
    setTimeout(() => {
        document.querySelectorAll('.alert').forEach(alert => {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        });
    }, 5000);
});
