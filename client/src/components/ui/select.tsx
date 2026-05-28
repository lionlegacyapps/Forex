import { cn } from '../../lib/utils';
import { forwardRef, SelectHTMLAttributes } from 'react';

const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(
  ({ className, ...props }, ref) => (
    <select
      className={cn(
        'flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:opacity-50',
        className
      )}
      ref={ref}
      {...props}
    />
  )
);
Select.displayName = 'Select';
export { Select };
