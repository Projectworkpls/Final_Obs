// Universal touch enhancements
document.addEventListener('DOMContentLoaded', function() {
    // Add touch feedback to all buttons
    const buttons = document.querySelectorAll('.btn');
    buttons.forEach(button => {
        button.classList.add('touch-feedback');
    });
    
    // Optimize tables for mobile
    const tables = document.querySelectorAll('.table');
    tables.forEach(table => {
        if (window.innerWidth <= 768) {
            table.classList.add('table-responsive');
        }
    });

    // Handle mobile navigation
    const navbarToggler = document.querySelector('.navbar-toggler');
    if (navbarToggler) {
        navbarToggler.addEventListener('click', function() {
            document.querySelector('.navbar-collapse').classList.toggle('show');
        });
    }

    // Optimize modals for mobile
    const modals = document.querySelectorAll('.modal');
    modals.forEach(modal => {
        modal.addEventListener('show.bs.modal', function() {
            if (window.innerWidth <= 768) {
                this.querySelector('.modal-dialog').classList.add('modal-fullscreen');
            }
        });
    });

    // Handle window resize
    window.addEventListener('resize', function() {
        const tables = document.querySelectorAll('.table');
        tables.forEach(table => {
            if (window.innerWidth <= 768) {
                table.classList.add('table-responsive');
            } else {
                table.classList.remove('table-responsive');
            }
        });
    });
}); 