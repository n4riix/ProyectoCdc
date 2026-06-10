document.addEventListener('DOMContentLoaded', () => {
    // Obtenemos el tema guardado. Si es la primera vez que el usuario entra, será 'null'
    const savedTheme = localStorage.getItem('theme');
    const body = document.body;
    
    // La Magia: Si el tema es 'dark' o si está en blanco (null), forzamos el modo oscuro
    if (savedTheme === 'dark' || savedTheme === null) {
        body.classList.add('dark-mode');
        actualizarLogos(true);
        
        // Guardamos la preferencia oscura de una vez para sus futuras visitas
        if (savedTheme === null) {
            localStorage.setItem('theme', 'dark');
        }
    } else {
        // Solo si explícitamente el usuario eligió 'light' en el pasado
        actualizarLogos(false);
    }

    // Escuchamos los clics en el botón de cambiar tema
    const themeToggles = document.querySelectorAll('.theme-toggle');
    themeToggles.forEach(btn => {
        btn.addEventListener('click', () => {
            body.classList.toggle('dark-mode');
            const isDark = body.classList.contains('dark-mode');
            
            // Guardamos la nueva preferencia en el navegador
            localStorage.setItem('theme', isDark ? 'dark' : 'light');
            actualizarLogos(isDark);
        });
    });
});

function actualizarLogos(isDark) {
    const logos = document.querySelectorAll('.brand-logo');
    logos.forEach(logo => {
        if(isDark) {
            logo.src = logo.getAttribute('data-dark');
        } else {
            logo.src = logo.getAttribute('data-light');
        }
    });
}