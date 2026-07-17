const headers = document.querySelectorAll(".panel-header");

headers.forEach(header => {

    header.addEventListener("click", () => {

        header.classList.toggle("active");

        const content =
            header.nextElementSibling;

        content.classList.toggle("show");

    });

});