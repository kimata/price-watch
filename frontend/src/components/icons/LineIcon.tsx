interface LineIconProps {
    className?: string;
}

export default function LineIcon({ className }: LineIconProps) {
    return (
        <svg className={className} viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 2C6.48 2 2 5.69 2 10.2c0 4.04 3.58 7.42 8.42 8.07.33.07.77.22.89.5.1.26.07.66.03.92l-.14.87c-.04.26-.21.99.87.54 1.08-.44 5.84-3.44 7.97-5.89C21.66 13.2 22 11.74 22 10.2 22 5.69 17.52 2 12 2zm-3.39 11a.5.5 0 01-.5-.5v-4a.5.5 0 011 0v3.5h1.89a.5.5 0 010 1H8.61zm2.89-.5a.5.5 0 01-1 0v-4a.5.5 0 011 0v4zm3.5 0a.5.5 0 01-.5.5h-.5a.5.5 0 01-.42-.23L12.5 10.5v2a.5.5 0 01-1 0v-4a.5.5 0 01.5-.5h.5a.5.5 0 01.42.23l1.08 1.77v-2a.5.5 0 011 0v4zm3 0a.5.5 0 01-1 0v-1.5h-1v1.5a.5.5 0 01-1 0v-4a.5.5 0 011 0v1.5h1v-1.5a.5.5 0 011 0v4z" />
        </svg>
    );
}
