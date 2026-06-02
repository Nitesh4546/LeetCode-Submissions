class Solution {
    public int[] plusOne(int[] digits) {
        int n = digits.length;
        // int arr[] = new int[n];

        int res[] = new int[n];
        // arr[n-1] = 1;//arr = {0,0,0,1}
        int c = 0;
        int i = n-1;
        while(i>=0){
            // int val1 = (i>=0)? digits[i]: 0;
            // int val2 = (i>=0)? arr[i]: 0;

            // int sum = val1+val2+c;
            int val = (i==n-1)? 1:0;
            res[i] = digits[i]+val+c;

            // if(sum>=10){
                // res[i] = sum%10;
                // c = 1;
            // }else{
                // res[i] = sum;
                // c = 0;
            // }
            if(res[i]>=10){
                res[i]%=10;
                c=1;
            }else{
                c=0;
            }
            i--;
        }
        if(c==1){
            int out[] = new int[n+1];
            out[0] = 1;
            for(int k=1;k<=n;k++){
                out[k] = res[k-1];
            }
            return out;
        }
        return res;
    }
}